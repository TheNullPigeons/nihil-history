from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from nihil_history.services import hosts_add, hosts_list


def _host_exists(ip: str) -> bool:
    return any(host.ip == ip for host in hosts_list())


def import_nmap_xml(path: str) -> dict[str, int]:
    xml_path = Path(path)
    root = ET.fromstring(xml_path.read_text(encoding="utf-8", errors="ignore"))
    added_hosts = 0

    for host in root.findall(".//host"):
        addr = host.find("./address[@addrtype='ipv4']")
        if addr is None:
            continue
        ip = addr.attrib.get("addr")
        if not ip or _host_exists(ip):
            continue

        hostname_node = host.find("./hostnames/hostname")
        hostname = hostname_node.attrib.get("name") if hostname_node is not None else None

        os_name = None
        osmatch = host.find("./os/osmatch")
        if osmatch is not None:
            os_name = osmatch.attrib.get("name")

        hosts_add(ip=ip, hostname=hostname, domain=None, operating_system=os_name, source="nmap")
        added_hosts += 1

    return {"hosts": added_hosts}
