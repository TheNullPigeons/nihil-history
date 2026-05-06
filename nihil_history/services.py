from __future__ import annotations

from collections.abc import Iterable
import json
from pathlib import Path

from sqlalchemy import select

from nihil_history.config import env_file_path, key_path, load_config, save_config
from nihil_history.crypto import decrypt_secret, encrypt_secret, load_or_create_key
from nihil_history.db import get_session, init_db
from nihil_history.models import AccessLink, Credential, Engagement, Host
from nihil_history import nxc
from nihil_history.validators import (
    validate_domain,
    validate_ip,
    validate_protocol,
    validate_status,
)


class MissingEngagementError(RuntimeError):
    pass


def ensure_default_engagement() -> None:
    """Create and activate 'default' engagement if none exists."""
    init_db()
    cfg = load_config()
    if not cfg.current_engagement:
        with get_session() as session:
            any_engagement = session.scalar(select(Engagement).limit(1))
        if any_engagement is None:
            engagement_init("default")


def _current_engagement_name() -> str:
    ensure_default_engagement()
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


def engagement_init(name: str, nxc_workspace: str | None = None) -> Engagement:
    init_db()
    cfg = load_config()
    workspace = nxc_workspace or name
    with get_session() as session:
        existing = session.scalar(select(Engagement).where(Engagement.name == name))
        if existing is None:
            existing = Engagement(name=name, nxc_workspace=workspace)
            session.add(existing)
        elif existing.nxc_workspace != workspace:
            existing.nxc_workspace = workspace
        session.commit()
        session.refresh(existing)
    cfg.current_engagement = name
    save_config(cfg)
    nxc.ensure_workspace(workspace)
    try:
        write_env_file()
    except Exception:
        pass
    return existing


def engagement_use(name: str) -> Engagement:
    init_db()
    with get_session() as session:
        existing = session.scalar(select(Engagement).where(Engagement.name == name))
        if existing is None:
            raise MissingEngagementError(f"Engagement '{name}' does not exist.")
        workspace = existing.nxc_workspace or existing.name
    cfg = load_config()
    cfg.current_engagement = name
    save_config(cfg)
    nxc.ensure_workspace(workspace)
    try:
        write_env_file()
    except Exception:
        pass
    return existing


def engagement_set_workspace(name: str, workspace: str) -> Engagement:
    init_db()
    with get_session() as session:
        existing = session.scalar(select(Engagement).where(Engagement.name == name))
        if existing is None:
            raise MissingEngagementError(f"Engagement '{name}' does not exist.")
        existing.nxc_workspace = workspace
        session.commit()
        session.refresh(existing)
    cfg = load_config()
    if cfg.current_engagement == name:
        nxc.ensure_workspace(workspace)
    return existing


def engagement_list() -> list[Engagement]:
    init_db()
    with get_session() as session:
        return list(session.scalars(select(Engagement).order_by(Engagement.created_at.desc())).all())


def engagement_rename(old_name: str, new_name: str) -> Engagement:
    init_db()
    with get_session() as session:
        entry = session.scalar(select(Engagement).where(Engagement.name == old_name))
        if entry is None:
            raise MissingEngagementError(f"Engagement '{old_name}' does not exist.")
        conflict = session.scalar(select(Engagement).where(Engagement.name == new_name))
        if conflict is not None:
            raise ValueError(f"Engagement '{new_name}' already exists. Use merge to combine them.")
        entry.name = new_name
        session.commit()
        session.refresh(entry)
    cfg = load_config()
    if cfg.current_engagement == old_name:
        cfg.current_engagement = new_name
        save_config(cfg)
        try:
            write_env_file()
        except Exception:
            pass
    return entry


def engagement_merge(src_name: str, dst_name: str) -> Engagement:
    """Move all data from src into dst, then delete src."""
    init_db()
    with get_session() as session:
        src = session.scalar(select(Engagement).where(Engagement.name == src_name))
        if src is None:
            raise MissingEngagementError(f"Engagement '{src_name}' does not exist.")
        dst = session.scalar(select(Engagement).where(Engagement.name == dst_name))
        if dst is None:
            raise MissingEngagementError(f"Engagement '{dst_name}' does not exist.")
        from sqlalchemy import update as sa_update
        session.execute(sa_update(Credential).where(Credential.engagement_id == src.id).values(engagement_id=dst.id))
        session.execute(sa_update(Host).where(Host.engagement_id == src.id).values(engagement_id=dst.id))
        session.execute(sa_update(AccessLink).where(AccessLink.engagement_id == src.id).values(engagement_id=dst.id))
        session.delete(src)
        session.commit()
        session.refresh(dst)
    cfg = load_config()
    if cfg.current_engagement == src_name:
        cfg.current_engagement = dst_name
        save_config(cfg)
        try:
            write_env_file()
        except Exception:
            pass
    return dst


def engagement_delete(name: str) -> None:
    init_db()
    with get_session() as session:
        entry = session.scalar(select(Engagement).where(Engagement.name == name))
        if entry is None:
            raise MissingEngagementError(f"Engagement '{name}' does not exist.")
        session.delete(entry)
        session.commit()
    cfg = load_config()
    if cfg.current_engagement == name:
        cfg.current_engagement = None
        save_config(cfg)
        try:
            write_env_file()
        except Exception:
            pass


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


def _materialize_credential_secrets(entry: Credential) -> Credential:
    entry.password = _decrypted_secret(entry.password)
    entry.hash = _decrypted_secret(entry.hash)
    entry.secret = _decrypted_secret(entry.secret)
    return entry


def creds_add(
    username: str | None,
    password: str | None,
    hash: str | None,
    secret: str | None,
    domain: str | None,
    source: str = "manual",
) -> Credential:
    init_db()
    domain = validate_domain(domain)
    with get_session() as session:
        cred = Credential(
            engagement_id=_engagement_id(),
            username=username or None,
            password=_normalized_secret_for_storage(password),
            hash=_normalized_secret_for_storage(hash),
            secret=_normalized_secret_for_storage(secret),
            domain=domain,
            source=source,
        )
        session.add(cred)
        session.commit()
        session.refresh(cred)
        return _materialize_credential_secrets(cred)


def creds_list() -> list[Credential]:
    with get_session() as session:
        rows = list(session.scalars(select(Credential).where(Credential.engagement_id == _engagement_id()).order_by(Credential.id)).all())
        return [_materialize_credential_secrets(row) for row in rows]


def creds_set(cred_id: int) -> Credential:
    eid = _engagement_id()
    with get_session() as session:
        cred = session.scalar(select(Credential).where(Credential.id == cred_id, Credential.engagement_id == eid))
        if cred is None:
            raise ValueError(f"Credential {cred_id} not found in active engagement.")
    cfg = load_config()
    cfg.selected_cred_id = cred_id
    save_config(cfg)
    try:
        write_env_file()
    except Exception:
        pass
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
    username: str | None,
    password: str | None,
    hash: str | None,
    secret: str | None,
    domain: str | None,
) -> Credential:
    eid = _engagement_id()
    domain = validate_domain(domain)
    with get_session() as session:
        cred = session.scalar(select(Credential).where(Credential.id == cred_id, Credential.engagement_id == eid))
        if cred is None:
            raise ValueError(f"Credential {cred_id} not found in active engagement.")
        cred.username = username or None
        cred.password = _normalized_secret_for_storage(password)
        cred.hash = _normalized_secret_for_storage(hash)
        cred.secret = _normalized_secret_for_storage(secret)
        cred.domain = domain
        session.commit()
        session.refresh(cred)
        return _materialize_credential_secrets(cred)


def hosts_add(ip: str | None, hostname: str | None, domain: str | None, operating_system: str | None, role: str | None = None, source: str = "manual") -> Host:
    init_db()
    ip = validate_ip(ip) if ip else None
    domain = validate_domain(domain)
    with get_session() as session:
        host = Host(
            engagement_id=_engagement_id(),
            ip=ip,
            hostname=hostname,
            domain=domain,
            operating_system=operating_system,
            role=role.upper() if role else None,
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
    if host.role:
        cfg.selected_role_hosts[host.role.upper()] = host_id
    save_config(cfg)
    try:
        write_env_file()
    except Exception:
        pass
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


def hosts_update(host_id: int, ip: str | None, hostname: str | None, domain: str | None, operating_system: str | None, role: str | None = None) -> Host:
    eid = _engagement_id()
    ip = validate_ip(ip) if ip else None
    domain = validate_domain(domain)
    with get_session() as session:
        host = session.scalar(select(Host).where(Host.id == host_id, Host.engagement_id == eid))
        if host is None:
            raise ValueError(f"Host {host_id} not found in active engagement.")
        host.ip = ip
        host.hostname = hostname
        host.domain = domain
        host.operating_system = operating_system
        host.role = role.upper() if role else None
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
                "password": c.password if include_secrets else None,
                "hash": c.hash if include_secrets else None,
                "secret": c.secret if include_secrets else None,
                "source": c.source,
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
        "| ID | Username | Domain | Password | Hash | Secret | Source |",
        "|---:|---|---|---|---|---|---|",
    ]
    for item in data["credentials"]:
        password = item["password"] if include_secrets and item["password"] else "-"
        hash_ = item["hash"] if include_secrets and item["hash"] else "-"
        secret = item["secret"] if include_secrets and item["secret"] else "-"
        lines.append(
            f"| {item['id']} | {item['username'] or '-'} | {item['domain'] or '-'} | {password} | {hash_} | {secret} | {item['source']} |"
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


def write_env_file(shell: str = "zsh") -> Path:
    """Write current env exports to ~/.nihil-history/env.sh and return the path."""
    rows = list(env_exports())
    path = env_file_path()
    lines = [f"# nihil-history env - auto-generated, do not edit\n"]
    for key, value in rows:
        escaped = value.replace('"', '\\"')
        if shell == "fish":
            lines.append(f'set -gx {key} "{escaped}"\n')
        else:
            lines.append(f'export {key}="{escaped}"\n')
    path.write_text("".join(lines), encoding="utf-8")
    return path


_SHELL_BLOCK_BEGIN = "# >>> nihil-history shell integration >>>"
_SHELL_BLOCK_END = "# <<< nihil-history shell integration <<<"


def _shell_integration_block(env_path: Path) -> str:
    src_line = f'[ -f "{env_path}" ] && source "{env_path}"'
    return "\n".join([
        _SHELL_BLOCK_BEGIN,
        src_line,
        "nhi() {",
        '  command nhi "$@"',
        f"  {src_line}",
        "}",
        "nhit() {",
        '  command nhit "$@"',
        f"  {src_line}",
        "}",
        "nihil-history() {",
        '  command nihil-history "$@"',
        f"  {src_line}",
        "}",
        _SHELL_BLOCK_END,
        "",
    ])


def install_shell_integration(shell: str | None = None) -> Path:
    """Append (or refresh) the auto-source block in the user's shell rc file.

    Returns the rc file path that was patched.
    """
    import os
    if shell is None:
        shell = Path(os.environ.get("SHELL", "/bin/bash")).name

    home = Path.home()
    rc_map = {
        "zsh": home / ".zshrc",
        "bash": home / ".bashrc",
    }
    if shell not in rc_map:
        raise ValueError(f"Unsupported shell '{shell}'. Use zsh or bash.")
    rc_path = rc_map[shell]

    env_path = env_file_path()
    block = _shell_integration_block(env_path)

    existing = rc_path.read_text(encoding="utf-8") if rc_path.exists() else ""

    if _SHELL_BLOCK_BEGIN in existing and _SHELL_BLOCK_END in existing:
        before, _, rest = existing.partition(_SHELL_BLOCK_BEGIN)
        _, _, after = rest.partition(_SHELL_BLOCK_END)
        after = after.lstrip("\n")
        new_content = before.rstrip("\n") + "\n\n" + block + after
    else:
        sep = "" if existing.endswith("\n") or not existing else "\n"
        new_content = existing + sep + "\n" + block

    rc_path.write_text(new_content, encoding="utf-8")
    try:
        write_env_file(shell=shell)
    except Exception:
        pass
    return rc_path


def uninstall_shell_integration(shell: str | None = None) -> Path | None:
    """Remove the auto-source block from the user's shell rc file."""
    import os

    if shell is None:
        shell = Path(os.environ.get("SHELL", "/bin/bash")).name

    home = Path.home()
    rc_map = {
        "zsh": home / ".zshrc",
        "bash": home / ".bashrc",
    }
    if shell not in rc_map:
        raise ValueError(f"Unsupported shell '{shell}'. Use zsh or bash.")
    rc_path = rc_map[shell]
    if not rc_path.exists():
        return None
    existing = rc_path.read_text(encoding="utf-8")
    if _SHELL_BLOCK_BEGIN not in existing:
        return None
    before, _, rest = existing.partition(_SHELL_BLOCK_BEGIN)
    _, _, after = rest.partition(_SHELL_BLOCK_END)
    after = after.lstrip("\n")
    new_content = before.rstrip("\n") + ("\n" if after else "") + after
    rc_path.write_text(new_content, encoding="utf-8")
    return rc_path


def env_exports() -> Iterable[tuple[str, str]]:
    creds = creds_list()
    hosts = hosts_list()
    cfg = load_config()

    if creds:
        selected_cred = next((c for c in creds if c.id == cfg.selected_cred_id), creds[-1])
        if selected_cred.username:
            yield ("USER", selected_cred.username)
        if selected_cred.password:
            yield ("PASSWORD", selected_cred.password)
        if selected_cred.hash:
            yield ("NT_HASH", selected_cred.hash)
        if selected_cred.domain:
            yield ("DOMAIN", selected_cred.domain)
    if hosts:
        hosts_by_id = {h.id: h for h in hosts}
        selected_host = hosts_by_id.get(cfg.selected_host_id) or hosts[-1]
        if selected_host.ip:
            yield ("TARGET", selected_host.ip)
            yield ("IP", selected_host.ip)
        # Role-specific vars - each role maintains its own selected host
        for role_upper, host_id in (cfg.selected_role_hosts or {}).items():
            host = hosts_by_id.get(host_id)
            if host is None:
                continue
            if role_upper == "DC":
                if host.ip:
                    yield ("DC_IP", host.ip)
                if host.hostname:
                    yield ("DC_HOST", host.hostname)
