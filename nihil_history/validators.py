from __future__ import annotations

import ipaddress
import re

ALLOWED_PROTOCOLS = {"smb", "winrm", "rdp", "ssh", "ldap", "http", "https", "mssql", "wmi", "ftp"}
ALLOWED_STATUS = {"valid", "invalid", "unknown"}
ALLOWED_CRED_TYPES = {
    "password",
    "hash",
    "key",
    "ticket",
    "secret",
    "ntlm",
    "kerberos",
    "aes",
    "krb5ccache",
    "ssh_key",
    "pfx",
    "pem_key",
    "certificate",
    "api_key",
    "bearer",
    "cookie",
    "otp_seed",
    "token",
}
KNOWN_SECRET_FORMATS = {
    "ntlm",
    "lm",
    "rc4",
    "aes128",
    "aes256",
    "md5",
    "sha1",
    "sha256",
    "sha512",
    "krb5ccache",
    "jwt",
    "pkcs12",
    "pem",
}
CREDS_TYPE_ALIASES = {
    "pass": "password",
    "cert": "certificate",
}
SECRET_FORMAT_ALIASES = {
    "hash": "ntlm",
    "nthash": "ntlm",
    "ccache": "krb5ccache",
    "pfx": "pkcs12",
    "bearer": "jwt",
}
SECRET_FORMAT_RE = re.compile(r"^[A-Za-z0-9._:+-]{2,64}$")
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


def validate_cred_type(value: str) -> str:
    clean = require_non_empty(value, "type").lower()
    clean = CREDS_TYPE_ALIASES.get(clean, clean)
    if clean not in ALLOWED_CRED_TYPES:
        allowed = ", ".join(sorted(ALLOWED_CRED_TYPES))
        aliases = ", ".join(f"{alias}->{target}" for alias, target in sorted(CREDS_TYPE_ALIASES.items()))
        raise ValueError(f"Invalid credential type '{clean}'. Allowed: {allowed}. Aliases: {aliases}")
    return clean


def validate_secret_format(value: str | None) -> str | None:
    if value is None:
        return None
    clean = value.strip().lower()
    if not clean:
        return None
    clean = SECRET_FORMAT_ALIASES.get(clean, clean)
    if clean in KNOWN_SECRET_FORMATS:
        return clean
    if not SECRET_FORMAT_RE.fullmatch(clean):
        known = ", ".join(sorted(KNOWN_SECRET_FORMATS))
        raise ValueError(f"Invalid secret format '{clean}'. Known: {known}")
    # Allow custom formats for edge cases while keeping sane characters.
    return clean
