from __future__ import annotations

import re
from pathlib import Path

from nihil_history.services import access_link, creds_add, creds_list, hosts_add, hosts_list

NXC_SUCCESS_RE = re.compile(
    r"(?P<ip>\d+\.\d+\.\d+\.\d+)\s+\d+\s+(?P<host>[A-Za-z0-9_.-]+)\s+\[\+\]\s+(?P<domain>[^\\\s]+)\\(?P<user>[^\s:]+):(?P<secret>\S+)"
)


def _cred_exists(username: str, domain: str | None, password: str) -> int | None:
    for cred in creds_list():
        if cred.username == username and cred.domain == domain and (cred.password or "") == password:
            return cred.id
    return None


def _host_exists(ip: str) -> int | None:
    for host in hosts_list():
        if host.ip == ip:
            return host.id
    return None


def import_nxc_text(path: str) -> dict[str, int]:
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    added_creds = 0
    added_hosts = 0
    added_links = 0

    for line in content.splitlines():
        match = NXC_SUCCESS_RE.search(line)
        if not match:
            continue

        ip = match.group("ip")
        hostname = match.group("host")
        domain = match.group("domain")
        username = match.group("user")
        secret = match.group("secret")

        cred_id = _cred_exists(username=username, domain=domain, password=secret)
        if cred_id is None:
            cred = creds_add(username=username, password=secret, hash=None, secret=None, domain=domain, source="nxc")
            cred_id = cred.id
            added_creds += 1

        host_id = _host_exists(ip=ip)
        if host_id is None:
            host = hosts_add(ip=ip, hostname=hostname, domain=domain, operating_system=None, source="nxc")
            host_id = host.id
            added_hosts += 1

        access_link(cred_id=cred_id, host_id=host_id, protocol="smb", status="valid", source="nxc")
        added_links += 1

    return {"creds": added_creds, "hosts": added_hosts, "links": added_links}
