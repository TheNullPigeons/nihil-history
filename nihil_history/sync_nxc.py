from __future__ import annotations

import sqlite3
from pathlib import Path

from nihil_history.services import access_link, access_list, creds_add, creds_list, hosts_add, hosts_list

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


def _host_id_by_ip(ip: str) -> int | None:
    for host in hosts_list():
        if host.ip == ip:
            return host.id
    return None


def _import_links(db_path: Path, proto: str, source: str) -> int:
    """Build Access Matrix links from NXC admin/loggedin relations.

    An entry in admin_relations or loggedin_relations means the credential
    authenticated successfully on the host, so we record a "valid" link. Both
    tables collapse to the same status (the matrix has no dedicated admin state).
    """
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        rel_tables = [t for t in ("admin_relations", "loggedin_relations") if t in tables]
        if "users" not in tables or "hosts" not in tables or not rel_tables:
            conn.close()
            return 0
        users: dict[int, dict] = {}
        for uid, domain, username, password, credtype in cur.execute(
            "SELECT id, domain, username, password, credtype FROM users"
        ):
            users[uid] = {
                "username": username,
                "domain": domain,
                "password": password if credtype != "hash" else None,
                "hash": password if credtype == "hash" else None,
            }
        hosts = {hid: ip for hid, ip in cur.execute("SELECT id, ip FROM hosts")}
        pairs: set[tuple[int, int]] = set()
        for table in rel_tables:
            for userid, hostid in cur.execute(f"SELECT userid, hostid FROM {table}"):
                pairs.add((userid, hostid))
        conn.close()
    except Exception:
        return 0

    existing = {(link.cred_id, link.host_id, link.protocol) for link in access_list()}
    added = 0
    for userid, hostid in pairs:
        user = users.get(userid)
        ip = hosts.get(hostid)
        if not user or not user["username"] or not ip:
            continue
        cred_id = _cred_exists(user["username"], user["domain"], user["password"], user["hash"])
        host_id = _host_id_by_ip(ip)
        if cred_id is None or host_id is None:
            continue
        if (cred_id, host_id, proto) in existing:
            continue
        try:
            access_link(cred_id=cred_id, host_id=host_id, protocol=proto, status="valid", source=source)
        except ValueError:
            continue
        existing.add((cred_id, host_id, proto))
        added += 1
    return added


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

        # Access Matrix: derive cred<->host links from NXC admin/loggedin
        # relations (runs after creds + hosts are imported so they resolve).
        for db_file in _DB_QUERIES:
            db_path = workspace / db_file
            if not db_path.is_file():
                continue
            proto = db_file.replace(".db", "")
            added_links += _import_links(db_path, proto, source)

    return {"creds": added_creds, "hosts": added_hosts, "links": added_links}
