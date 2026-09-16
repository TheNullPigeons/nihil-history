from __future__ import annotations

import ipaddress
import sqlite3
from pathlib import Path

from nihil_history.services import access_link, access_list, creds_add, creds_list, hosts_add, hosts_list
from nihil_history.validators import validate_domain

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


def _clean_domain(v: str | None) -> str | None:
    """Reduce a raw NXC domain value to what creds_add will actually persist.

    NXC records placeholder domains like "." for local/standalone accounts,
    which fail domain validation and get silently stored as None. Applying
    the same normalization here keeps duplicate-detection in sync with what
    ends up in the database, instead of comparing against a value that was
    never actually stored.
    """
    try:
        return validate_domain(v)
    except ValueError:
        return None


def _norm_secret(v: str | None) -> str | None:
    """Normalize secret value - strip only, preserve case (passwords/hashes are case-sensitive)."""
    return v.strip() if v else None


def _cred_key(username: str | None, domain: str | None, password: str | None, hash_: str | None) -> tuple:
    return (_norm(username), _norm(domain), _norm_secret(password) or _norm_secret(hash_))


def _build_cred_index(creds) -> dict[tuple, int]:
    return {_cred_key(c.username, c.domain, c.password, c.hash): c.id for c in creds}


def _build_host_index(hosts) -> tuple[set[tuple], dict[str, int]]:
    pairs = {(h.ip, h.hostname or None) for h in hosts}
    by_ip = {h.ip: h.id for h in hosts if h.ip}
    return pairs, by_ip


def _import_links(db_path: Path, proto: str, source: str, cred_index: dict[tuple, int], host_by_ip: dict[str, int]) -> int:
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
        cred_id = cred_index.get(_cred_key(user["username"], user["domain"], user["password"], user["hash"]))
        host_id = host_by_ip.get(ip)
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
                "domain": _clean_domain(domain),
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
            if ip:
                try:
                    ipaddress.ip_address(ip.strip())
                except ValueError:
                    hostname = hostname or ip
                    ip = None
            results.append({"ip": ip, "hostname": hostname, "domain": domain, "os": os_name, "source": source})
        conn.close()
    except Exception:
        pass
    return results


def _workspace_dir(workspace_name: str, workspaces_path: str | None = None) -> Path:
    root = Path(workspaces_path).expanduser() if workspaces_path else _DEFAULT_WORKSPACES.expanduser()
    return root / workspace_name


def _delete_rows_and_relations(db_path: Path, table: str, ids: list[int], relation_column: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.executemany(f"DELETE FROM {table} WHERE id = ?", [(i,) for i in ids])
        tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for rel in ("admin_relations", "loggedin_relations"):
            if rel in tables:
                cur.executemany(f"DELETE FROM {rel} WHERE {relation_column} = ?", [(i,) for i in ids])
        conn.commit()
    finally:
        conn.close()


def nxc_delete_credential(
    workspace_name: str,
    username: str,
    domain: str | None,
    password: str | None,
    hash_: str | None,
    workspaces_path: str | None = None,
) -> int:
    """Delete the matching credential row(s) from NXC's own workspace databases.

    Matches on username + secret (password or hash, whichever side has it) -
    same identity key used for dedup on import. Domain is only enforced when
    our side actually has one: NXC fills placeholder domains (".") for local
    accounts that get normalized away on import, so a strict domain match
    would miss the exact rows that caused the duplicate in the first place.
    """
    workspace = _workspace_dir(workspace_name, workspaces_path)
    if not workspace.is_dir():
        return 0
    username_n = _norm(username)
    domain_n = _norm(domain)
    secret = _norm_secret(password) or _norm_secret(hash_)
    deleted = 0
    for db_file, (cred_q, _host_q) in _DB_QUERIES.items():
        if not cred_q:
            continue
        db_path = workspace / db_file
        if not db_path.is_file():
            continue
        table = "users" if "FROM users" in cred_q else "credentials"
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cols = {r[1] for r in cur.execute(f"PRAGMA table_info({table})")}
            has_domain = "domain" in cols
            fields = ["id", "username", "password"] + (["domain"] if has_domain else [])
            rows = cur.execute(f"SELECT {', '.join(fields)} FROM {table}").fetchall()
            conn.close()
        except Exception:
            continue
        to_delete = []
        for row in rows:
            values = dict(zip(fields, row))
            if _norm(values.get("username")) != username_n:
                continue
            if _norm_secret(values.get("password")) != secret:
                continue
            if domain_n is not None and has_domain:
                if _norm(_clean_domain(values.get("domain"))) != domain_n:
                    continue
            to_delete.append(values["id"])
        if to_delete:
            try:
                _delete_rows_and_relations(db_path, table, to_delete, "userid")
                deleted += len(to_delete)
            except Exception:
                continue
    return deleted


def nxc_delete_host(
    workspace_name: str,
    ip: str | None,
    hostname: str | None,
    workspaces_path: str | None = None,
) -> int:
    """Delete the matching host row(s) from NXC's own workspace databases."""
    workspace = _workspace_dir(workspace_name, workspaces_path)
    if not workspace.is_dir():
        return 0
    deleted = 0
    for db_file, (_cred_q, host_q) in _DB_QUERIES.items():
        if not host_q:
            continue
        db_path = workspace / db_file
        if not db_path.is_file():
            continue
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cols = {r[1] for r in cur.execute("PRAGMA table_info(hosts)")}
            has_hostname = "hostname" in cols
            fields = ["id", "ip"] + (["hostname"] if has_hostname else [])
            rows = cur.execute(f"SELECT {', '.join(fields)} FROM hosts").fetchall()
            conn.close()
        except Exception:
            continue
        to_delete = []
        for row in rows:
            values = dict(zip(fields, row))
            rip = values.get("ip")
            rhostname = values.get("hostname") if has_hostname else None
            if ip and rip and rip.strip() == ip.strip():
                to_delete.append(values["id"])
            elif not ip and hostname and rhostname and rhostname.strip().lower() == hostname.strip().lower():
                to_delete.append(values["id"])
        if to_delete:
            try:
                _delete_rows_and_relations(db_path, "hosts", to_delete, "hostid")
                deleted += len(to_delete)
            except Exception:
                continue
    return deleted


def import_nxc_db(workspaces_path: str | None = None, workspace_name: str | None = None) -> dict[str, int]:
    root = Path(workspaces_path).expanduser() if workspaces_path else _DEFAULT_WORKSPACES.expanduser()
    if not root.exists():
        raise FileNotFoundError(f"NXC workspaces directory not found: {root}")

    added_creds = added_hosts = added_links = 0

    if workspace_name:
        candidates = [root / workspace_name]
    else:
        candidates = sorted(root.iterdir())

    # Fetch each table once and keep an in-memory index up to date as we
    # insert, instead of re-querying (and re-decrypting) the whole table for
    # every single NXC row - that O(n^2) pattern is what made syncing slow
    # on large histories.
    cred_index = _build_cred_index(creds_list())
    host_pairs, host_by_ip = _build_host_index(hosts_list())

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
            if not h["ip"] and not h["hostname"]:
                continue
            pair = (h["ip"], h["hostname"] or None)
            if pair in host_pairs:
                continue
            try:
                host = hosts_add(ip=h["ip"], hostname=h["hostname"], domain=h["domain"], operating_system=h.get("os"), source=h["source"])
            except ValueError:
                # Drop the unusable field and retry once - upstream NXC sometimes stores
                # whitespace-only or otherwise malformed domains we can't trust.
                host = hosts_add(ip=h["ip"], hostname=h["hostname"], domain=None, operating_system=h.get("os"), source=h["source"])
            host_pairs.add(pair)
            if host.ip:
                host_by_ip[host.ip] = host.id
            added_hosts += 1

        seen_creds: set[tuple] = set()
        for c in all_creds:
            if not c["username"]:
                continue
            key = _cred_key(c["username"], c["domain"], c["password"], c["hash"])
            if key in seen_creds:
                continue
            seen_creds.add(key)
            cred_id = cred_index.get(key)
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
                cred_index[_cred_key(cred.username, cred.domain, cred.password, cred.hash)] = cred_id
                added_creds += 1

        # Access Matrix: derive cred<->host links from NXC admin/loggedin
        # relations (runs after creds + hosts are imported so they resolve).
        for db_file in _DB_QUERIES:
            db_path = workspace / db_file
            if not db_path.is_file():
                continue
            proto = db_file.replace(".db", "")
            added_links += _import_links(db_path, proto, source, cred_index, host_by_ip)

    return {"creds": added_creds, "hosts": added_hosts, "links": added_links}
