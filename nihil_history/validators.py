from __future__ import annotations

import ipaddress
import re

ALLOWED_PROTOCOLS = {"smb", "winrm", "rdp", "ssh", "ldap", "http", "https", "mssql", "wmi", "ftp"}
ALLOWED_STATUS = {"valid", "invalid", "unknown"}
DOMAIN_RE = re.compile(r"^(?=.{1,255}$)([A-Za-z0-9-]+\.)*[A-Za-z0-9-]+$")


def require_non_empty(value: str, field: str) -> str:
    clean = value.strip()
    if not clean:
        raise ValueError(f"{field} must not be empty.")
    return clean


def validate_ip(value: str) -> str:
    clean = require_non_empty(value, "ip")
    try:
        ipaddress.ip_address(clean)
    except ValueError as exc:
        raise ValueError(f"Invalid IP address: {clean}") from exc
    return clean


def validate_domain(value: str | None) -> str | None:
    if value is None:
        return None
    clean = value.strip()
    if not clean:
        return None
    if not DOMAIN_RE.fullmatch(clean):
        raise ValueError(f"Invalid domain: {clean}")
    return clean.upper()


def validate_protocol(value: str) -> str:
    clean = require_non_empty(value, "protocol").lower()
    if clean not in ALLOWED_PROTOCOLS:
        allowed = ", ".join(sorted(ALLOWED_PROTOCOLS))
        raise ValueError(f"Invalid protocol '{clean}'. Allowed: {allowed}")
    return clean


def validate_status(value: str) -> str:
    clean = require_non_empty(value, "status").lower()
    if clean not in ALLOWED_STATUS:
        allowed = ", ".join(sorted(ALLOWED_STATUS))
        raise ValueError(f"Invalid status '{clean}'. Allowed: {allowed}")
    return clean


