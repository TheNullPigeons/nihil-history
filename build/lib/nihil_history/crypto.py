from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ENC_PREFIX = "enc$"


def load_or_create_key(key_path: Path) -> bytes:
    if key_path.exists():
        return key_path.read_bytes()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    return key


def encrypt_secret(secret: str, key: bytes) -> str:
    token = Fernet(key).encrypt(secret.encode("utf-8")).decode("utf-8")
    return f"{ENC_PREFIX}{token}"


def decrypt_secret(payload: str, key: bytes) -> str:
    if not payload.startswith(ENC_PREFIX):
        return payload
    token = payload[len(ENC_PREFIX) :]
    try:
        return Fernet(key).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt secret with current key.") from exc
