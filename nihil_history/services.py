from __future__ import annotations

from collections.abc import Iterable
import json

from sqlalchemy import select

from nihil_history.config import key_path, load_config, save_config
from nihil_history.crypto import decrypt_secret, encrypt_secret, load_or_create_key
from nihil_history.db import get_session, init_db
from nihil_history.models import AccessLink, Credential, Engagement, Host
from nihil_history.validators import (
    validate_cred_type,
    validate_domain,
    validate_ip,
    validate_protocol,
    validate_secret_format,
    validate_status,
    require_non_empty,
)


class MissingEngagementError(RuntimeError):
    pass


def _current_engagement_name() -> str:
    cfg = load_config()
    if not cfg.current_engagement:
        raise MissingEngagementError("No active engagement. Use `nhi engagement use <name>`.")
    return cfg.current_engagement


def require_engagement() -> Engagement:
    name = _current_engagement_name()
    with get_session() as session:
        entry = session.scalar(select(Engagement).where(Engagement.name == name))
        if entry is None:
            raise MissingEngagementError(f"Active engagement '{name}' does not exist anymore.")
        return entry


def engagement_init(name: str) -> Engagement:
    init_db()
    cfg = load_config()
    with get_session() as session:
        existing = session.scalar(select(Engagement).where(Engagement.name == name))
        if existing is None:
            existing = Engagement(name=name)
            session.add(existing)
            session.commit()
            session.refresh(existing)
    cfg.current_engagement = name
    save_config(cfg)
    return existing


def engagement_use(name: str) -> Engagement:
    init_db()
    with get_session() as session:
        existing = session.scalar(select(Engagement).where(Engagement.name == name))
        if existing is None:
            raise MissingEngagementError(f"Engagement '{name}' does not exist.")
    cfg = load_config()
    cfg.current_engagement = name
    save_config(cfg)
    return existing


def engagement_list() -> list[Engagement]:
    init_db()
    with get_session() as session:
        return list(session.scalars(select(Engagement).order_by(Engagement.created_at.desc())).all())


def _engagement_id() -> int:
    return require_engagement().id


def _normalized_secret_for_storage(secret: str | None) -> str | None:
    if secret is None:
        return None
    cfg = load_config()
    if not cfg.encryption_enabled:
        return secret
    key = load_or_create_key(key_path())
    return encrypt_secret(secret, key)


def _decrypted_secret(secret: str | None) -> str | None:
    if secret is None:
        return None
    cfg = load_config()
    if not cfg.encryption_enabled:
        return secret
    key = load_or_create_key(key_path())
    return decrypt_secret(secret, key)


def _materialize_credential_secret(entry: Credential) -> Credential:
    entry.secret = _decrypted_secret(entry.secret)
    return entry


def creds_add(
    username: str,
    secret: str | None,
    domain: str | None,
    cred_type: str,
    secret_format: str | None = None,
    source: str = "manual",
) -> Credential:
    init_db()
    username = require_non_empty(username, "username")
    domain = validate_domain(domain)
    cred_type = validate_cred_type(cred_type)
    secret_format = validate_secret_format(secret_format)
    with get_session() as session:
        cred = Credential(
            engagement_id=_engagement_id(),
            username=username,
            secret=_normalized_secret_for_storage(secret),
            domain=domain,
            cred_type=cred_type,
            secret_format=secret_format,
            source=source,
        )
        session.add(cred)
        session.commit()
        session.refresh(cred)
        return _materialize_credential_secret(cred)


def creds_list() -> list[Credential]:
    with get_session() as session:
        rows = list(session.scalars(select(Credential).where(Credential.engagement_id == _engagement_id()).order_by(Credential.id)).all())
        return [_materialize_credential_secret(row) for row in rows]


def creds_set(cred_id: int) -> Credential:
    eid = _engagement_id()
    with get_session() as session:
        cred = session.scalar(select(Credential).where(Credential.id == cred_id, Credential.engagement_id == eid))
        if cred is None:
            raise ValueError(f"Credential {cred_id} not found in active engagement.")
    cfg = load_config()
    cfg.selected_cred_id = cred_id
    save_config(cfg)
    return cred


def creds_remove(cred_id: int) -> None:
    eid = _engagement_id()
    with get_session() as session:
        cred = session.scalar(select(Credential).where(Credential.id == cred_id, Credential.engagement_id == eid))
        if cred is None:
            raise ValueError(f"Credential {cred_id} not found in active engagement.")
        links = session.scalars(select(AccessLink).where(AccessLink.cred_id == cred_id, AccessLink.engagement_id == eid)).all()
        for link in links:
            session.delete(link)
        session.delete(cred)
        session.commit()
    cfg = load_config()
    if cfg.selected_cred_id == cred_id:
        cfg.selected_cred_id = None
        save_config(cfg)


def creds_update(
    cred_id: int,
    username: str,
    secret: str | None,
    domain: str | None,
    cred_type: str,
    secret_format: str | None = None,
) -> Credential:
    eid = _engagement_id()
    username = require_non_empty(username, "username")
    domain = validate_domain(domain)
    cred_type = validate_cred_type(cred_type)
    secret_format = validate_secret_format(secret_format)
    with get_session() as session:
        cred = session.scalar(select(Credential).where(Credential.id == cred_id, Credential.engagement_id == eid))
        if cred is None:
            raise ValueError(f"Credential {cred_id} not found in active engagement.")
        cred.username = username
        cred.secret = _normalized_secret_for_storage(secret)
        cred.domain = domain
        cred.cred_type = cred_type
        cred.secret_format = secret_format
        session.commit()
        session.refresh(cred)
        return _materialize_credential_secret(cred)


def hosts_add(ip: str, hostname: str | None, domain: str | None, operating_system: str | None, source: str = "manual") -> Host:
    init_db()
    ip = validate_ip(ip)
    domain = validate_domain(domain)
    with get_session() as session:
        host = Host(
            engagement_id=_engagement_id(),
            ip=ip,
            hostname=hostname,
            domain=domain,
            operating_system=operating_system,
            note=f"source={source}",
        )
        session.add(host)
        session.commit()
        session.refresh(host)
        return host


def hosts_list() -> list[Host]:
    with get_session() as session:
        return list(session.scalars(select(Host).where(Host.engagement_id == _engagement_id()).order_by(Host.id)).all())


def hosts_set(host_id: int) -> Host:
    eid = _engagement_id()
    with get_session() as session:
        host = session.scalar(select(Host).where(Host.id == host_id, Host.engagement_id == eid))
        if host is None:
            raise ValueError(f"Host {host_id} not found in active engagement.")
    cfg = load_config()
    cfg.selected_host_id = host_id
    save_config(cfg)
    return host


def hosts_remove(host_id: int) -> None:
    eid = _engagement_id()
    with get_session() as session:
        host = session.scalar(select(Host).where(Host.id == host_id, Host.engagement_id == eid))
        if host is None:
            raise ValueError(f"Host {host_id} not found in active engagement.")
        links = session.scalars(select(AccessLink).where(AccessLink.host_id == host_id, AccessLink.engagement_id == eid)).all()
        for link in links:
            session.delete(link)
        session.delete(host)
        session.commit()
    cfg = load_config()
    if cfg.selected_host_id == host_id:
        cfg.selected_host_id = None
        save_config(cfg)


def hosts_update(host_id: int, ip: str, hostname: str | None, domain: str | None, operating_system: str | None) -> Host:
    eid = _engagement_id()
    ip = validate_ip(ip)
    domain = validate_domain(domain)
    with get_session() as session:
        host = session.scalar(select(Host).where(Host.id == host_id, Host.engagement_id == eid))
        if host is None:
            raise ValueError(f"Host {host_id} not found in active engagement.")
        host.ip = ip
        host.hostname = hostname
        host.domain = domain
        host.operating_system = operating_system
        session.commit()
        session.refresh(host)
        return host


def access_link(cred_id: int, host_id: int, protocol: str, status: str, source: str = "manual") -> AccessLink:
    init_db()
    eid = _engagement_id()
    protocol = validate_protocol(protocol)
    status = validate_status(status)
    with get_session() as session:
        cred = session.scalar(select(Credential).where(Credential.id == cred_id, Credential.engagement_id == eid))
        host = session.scalar(select(Host).where(Host.id == host_id, Host.engagement_id == eid))
        if cred is None:
            raise ValueError(f"Credential {cred_id} not found in active engagement.")
        if host is None:
            raise ValueError(f"Host {host_id} not found in active engagement.")
        link = AccessLink(
            engagement_id=eid,
            cred_id=cred_id,
            host_id=host_id,
            protocol=protocol,
            status=status,
            source=source,
        )
        session.add(link)
        session.commit()
        session.refresh(link)
        return link


def access_list() -> list[AccessLink]:
    with get_session() as session:
        return list(session.scalars(select(AccessLink).where(AccessLink.engagement_id == _engagement_id()).order_by(AccessLink.id)).all())


def access_remove(link_id: int) -> None:
    eid = _engagement_id()
    with get_session() as session:
        link = session.scalar(select(AccessLink).where(AccessLink.id == link_id, AccessLink.engagement_id == eid))
        if link is None:
            raise ValueError(f"Access link {link_id} not found in active engagement.")
        session.delete(link)
        session.commit()


def access_update(link_id: int, cred_id: int, host_id: int, protocol: str, status: str) -> AccessLink:
    eid = _engagement_id()
    protocol = validate_protocol(protocol)
    status = validate_status(status)
    with get_session() as session:
        link = session.scalar(select(AccessLink).where(AccessLink.id == link_id, AccessLink.engagement_id == eid))
        if link is None:
            raise ValueError(f"Access link {link_id} not found in active engagement.")
        cred = session.scalar(select(Credential).where(Credential.id == cred_id, Credential.engagement_id == eid))
        host = session.scalar(select(Host).where(Host.id == host_id, Host.engagement_id == eid))
        if cred is None:
            raise ValueError(f"Credential {cred_id} not found in active engagement.")
        if host is None:
            raise ValueError(f"Host {host_id} not found in active engagement.")
        link.cred_id = cred_id
        link.host_id = host_id
        link.protocol = protocol
        link.status = status
        session.commit()
        session.refresh(link)
        return link


def access_matrix() -> tuple[list[Host], list[Credential], dict[tuple[int, int], str]]:
    hosts = hosts_list()
    creds = creds_list()
    matrix: dict[tuple[int, int], str] = {}
    for link in access_list():
        matrix[(link.host_id, link.cred_id)] = f"{link.protocol}:{link.status}"
    return hosts, creds, matrix


def report_payload(include_secrets: bool = False) -> dict:
    engagement = require_engagement()
    creds = creds_list()
    hosts = hosts_list()
    links = access_list()
    return {
        "engagement": {"id": engagement.id, "name": engagement.name, "created_at": engagement.created_at.isoformat()},
        "credentials": [
            {
                "id": c.id,
                "username": c.username,
                "domain": c.domain,
                "type": c.cred_type,
                "format": c.secret_format,
                "source": c.source,
                "secret": c.secret if include_secrets else None,
            }
            for c in creds
        ],
        "hosts": [
            {
                "id": h.id,
                "ip": h.ip,
                "hostname": h.hostname,
                "domain": h.domain,
                "operating_system": h.operating_system,
            }
            for h in hosts
        ],
        "access_links": [
            {
                "id": l.id,
                "cred_id": l.cred_id,
                "host_id": l.host_id,
                "protocol": l.protocol,
                "status": l.status,
                "source": l.source,
            }
            for l in links
        ],
    }


def export_report_json(include_secrets: bool = False) -> str:
    return json.dumps(report_payload(include_secrets=include_secrets), indent=2)


def export_report_markdown(include_secrets: bool = False) -> str:
    data = report_payload(include_secrets=include_secrets)
    lines = [
        f"# nihil-history report - {data['engagement']['name']}",
        "",
        "## Credentials",
        "",
        "| ID | Username | Domain | Type | Format | Source | Secret |",
        "|---:|---|---|---|---|---|---|",
    ]
    for item in data["credentials"]:
        secret = item["secret"] if include_secrets and item["secret"] else "-"
        lines.append(
            f"| {item['id']} | {item['username']} | {item['domain'] or '-'} | {item['type']} | {item['format'] or '-'} | {item['source']} | {secret} |"
        )
    lines.extend(["", "## Hosts", "", "| ID | IP | Hostname | Domain | OS |", "|---:|---|---|---|---|"])
    for item in data["hosts"]:
        lines.append(
            f"| {item['id']} | {item['ip']} | {item['hostname'] or '-'} | {item['domain'] or '-'} | {item['operating_system'] or '-'} |"
        )
    lines.extend(["", "## Access Links", "", "| ID | Cred ID | Host ID | Protocol | Status | Source |", "|---:|---:|---:|---|---|---|"])
    for item in data["access_links"]:
        lines.append(
            f"| {item['id']} | {item['cred_id']} | {item['host_id']} | {item['protocol']} | {item['status']} | {item['source']} |"
        )
    return "\n".join(lines)


def env_exports() -> Iterable[tuple[str, str]]:
    creds = creds_list()
    hosts = hosts_list()
    cfg = load_config()

    if creds:
        selected_cred = next((c for c in creds if c.id == cfg.selected_cred_id), creds[-1])
        yield ("NIHIL_USER", selected_cred.username)
        if selected_cred.secret:
            if selected_cred.cred_type in {"ntlm", "hash"} or selected_cred.secret_format in {"ntlm", "lm", "rc4"}:
                yield ("NIHIL_HASH", selected_cred.secret)
            else:
                yield ("NIHIL_PASS", selected_cred.secret)
        if selected_cred.domain:
            yield ("NIHIL_DOMAIN", selected_cred.domain)
    if hosts:
        selected_host = next((h for h in hosts if h.id == cfg.selected_host_id), hosts[-1])
        yield ("NIHIL_TARGET", selected_host.ip)
        if selected_host.hostname:
            yield ("NIHIL_HOSTNAME", selected_host.hostname)
