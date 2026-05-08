from __future__ import annotations

import sqlite3
from pathlib import Path

from nihil_history.services import access_link, creds_add, creds_list, hosts_add, hosts_list

_DEFAULT_WORKSPACES = Path("~/.nxc/workspaces")

# (cred_query, host_query) - empty string means skip
_DB_QUERIES: dict[str, tuple[str, str]] = {
    "smb.db": (
        "SELECT username, password, domain, credtype FROM users",
        "SELECT ip, hostname, domain, os FROM hosts",
    ),
    "ldap.db": (
        "SELECT username, password, domain, credtype FROM users",
        "SELECT ip, hostname, domain, os FROM hosts",
    ),
    "mssql.db": (
        "SELECT username, password, domain, credtype FROM users",
        "SELECT ip, hostname, domain, os FROM hosts",
    ),
    "winrm.db": (
        "SELECT username, password, domain, credtype FROM users",
        "SELECT ip, hostname, domain, os FROM hosts",
    ),
    "ssh.db": (
        "SELECT username, password, credtype FROM credentials",
        "",
    ),
    "ftp.db": (
        "SELECT username, password FROM credentials",
        "",
    ),
    "wmi.db": (
        "SELECT username, password FROM credentials",
        "SELECT ip, hostname FROM hosts",
    ),
    "rdp.db": (
        "",
        "SELECT ip, hostname, domain FROM hosts",
    ),
}


def _norm(v: str | None) -> str | None:
    """Normalize for case-insensitive identity comparison (username, domain)."""
    return v.strip().lower() if v else None


def _norm_secret(v: str | None) -> str | None:
    """Normalize secret value - strip only, preserve case (passwords/hashes are case-sensitive)."""
    return v.strip() if v else None


def _cred_exists(username: str, domain: str | None, password: str | None, hash_: str | None) -> int | None:
    username_n = _norm(username)
    domain_n = _norm(domain)
    # treat hash and password as the same "secret" slot - NXC may classify differently across syncs
    secret = _norm_secret(password) or _norm_secret(hash_)
    for cred in creds_list():
        if _norm(cred.username) != username_n:
            continue
        if _norm(cred.domain) != domain_n:
            continue
        cred_secret = _norm_secret(cred.password) or _norm_secret(cred.hash)
        if secret == cred_secret:
            return cred.id
    return None


def _host_pair_exists(ip: str, hostname: str | None) -> bool:
    for host in hosts_list():
        if host.ip == ip and (host.hostname or None) == (hostname or None):
            return True
    return False


def _extract_creds(db_path: Path, query: str, source: str) -> list[dict]:
    results = []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            username = password = domain = credtype = None
            if "domain" in columns and "credtype" in columns:
                username, password, domain, credtype = row
            elif "credtype" in columns:
                username, password, credtype = row
            else:
                username, password = row
            results.append({
                "username": username,
                "password": password if credtype != "hash" else None,
                "hash": password if credtype == "hash" else None,
                "domain": domain,
                "source": source,
            })
        conn.close()
    except Exception:
        pass
    return results


def _extract_hosts(db_path: Path, query: str, source: str) -> list[dict]:
    results = []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            ip = hostname = domain = os_name = None
            if "os" in columns and "domain" in columns:
                ip, hostname, domain, os_name = row
                if hostname and domain and "." not in hostname:
                    hostname = f"{hostname}.{domain}"
            elif "domain" in columns:
                ip, hostname, domain = row
                if hostname and domain and "." not in hostname:
                    hostname = f"{hostname}.{domain}"
            elif "ip" in columns:
                ip, hostname = row
            else:
                hostname = row[0]
            results.append({"ip": ip, "hostname": hostname, "domain": domain, "os": os_name, "source": source})
        conn.close()
    except Exception:
        pass
    return results


def import_nxc_db(workspaces_path: str | None = None, workspace_name: str | None = None) -> dict[str, int]:
    root = Path(workspaces_path).expanduser() if workspaces_path else _DEFAULT_WORKSPACES.expanduser()
    if not root.exists():
        raise FileNotFoundError(f"NXC workspaces directory not found: {root}")

    added_creds = added_hosts = added_links = 0

    if workspace_name:
        candidates = [root / workspace_name]
    else:
        candidates = sorted(root.iterdir())

    for workspace in candidates:
        if not workspace.is_dir():
            continue
        source = f"nxc:{workspace.name}"

        all_creds: list[dict] = []
        all_hosts: list[dict] = []

        for db_file, (cred_q, host_q) in _DB_QUERIES.items():
            db_path = workspace / db_file
            if not db_path.is_file():
                continue
            proto = db_file.replace(".db", "")
            if cred_q:
                all_creds.extend(_extract_creds(db_path, cred_q, source))
            if host_q:
                all_hosts.extend(_extract_hosts(db_path, host_q, source))

        for h in all_hosts:
            if not h["ip"]:
                continue
            if _host_pair_exists(h["ip"], h["hostname"]):
                continue
            try:
                hosts_add(ip=h["ip"], hostname=h["hostname"], domain=h["domain"], operating_system=h.get("os"), source=h["source"])
            except ValueError:
                # Drop the unusable field and retry once - upstream NXC sometimes stores
                # whitespace-only or otherwise malformed domains we can't trust.
                hosts_add(ip=h["ip"], hostname=h["hostname"], domain=None, operating_system=h.get("os"), source=h["source"])
            added_hosts += 1

        seen_creds: set[tuple] = set()
        for c in all_creds:
            if not c["username"]:
                continue
            key = (_norm(c["username"]), _norm(c["domain"]), _norm_secret(c["password"]) or _norm_secret(c["hash"]))
            if key in seen_creds:
                continue
            seen_creds.add(key)
            cred_id = _cred_exists(c["username"], c["domain"], c["password"], c["hash"])
            if cred_id is None:
                try:
                    cred = creds_add(
                        username=c["username"],
                        password=c["password"],
                        hash=c["hash"],
                        secret=None,
                        domain=c["domain"],
                        source=c["source"],
                    )
                except ValueError:
                    cred = creds_add(
                        username=c["username"],
                        password=c["password"],
                        hash=c["hash"],
                        secret=None,
                        domain=None,
                        source=c["source"],
                    )
                cred_id = cred.id
                added_creds += 1

    return {"creds": added_creds, "hosts": added_hosts, "links": added_links}
