from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOME = Path.home() / ".nihil-history"


@dataclass(slots=True)
class AppConfig:
    db_path: Path
    current_engagement: str | None = None
    selected_cred_id: int | None = None
    selected_host_id: int | None = None
    selected_role_hosts: dict = None  # role (uppercase) -> host_id
    encryption_enabled: bool = False

    def __post_init__(self):
        if self.selected_role_hosts is None:
            object.__setattr__(self, "selected_role_hosts", {})


def _fallback_home() -> Path:
    return Path.cwd() / ".nihil-history"


def home_dir() -> Path:
    env_home = os.environ.get("NIHIL_HISTORY_HOME")
    if env_home:
        return Path(env_home).expanduser()
    return DEFAULT_HOME


def ensure_home() -> Path:
    target = home_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return target
    except OSError:
        fallback = _fallback_home()
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def default_db_path() -> Path:
    return ensure_home() / "history.db"


def config_path() -> Path:
    return ensure_home() / "config.json"


def env_file_path() -> Path:
    return ensure_home() / "env.sh"


def key_path() -> Path:
    return ensure_home() / "secret.key"


def load_config() -> AppConfig:
    cfg_path = config_path()
    default_db = default_db_path()
    if not cfg_path.exists():
        cfg = AppConfig(
            db_path=default_db,
            encryption_enabled=os.environ.get("NIHIL_HISTORY_ENCRYPTION", "0") == "1",
        )
        save_config(cfg)
        return cfg

    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except PermissionError:
        fallback_cfg = _fallback_home() / "config.json"
        if not fallback_cfg.exists():
            cfg = AppConfig(
                db_path=_fallback_home() / "history.db",
                encryption_enabled=os.environ.get("NIHIL_HISTORY_ENCRYPTION", "0") == "1",
            )
            save_config(cfg)
            return cfg
        raw = json.loads(fallback_cfg.read_text(encoding="utf-8"))
    db_path = Path(raw.get("db_path", str(default_db)))
    current_engagement = raw.get("current_engagement")
    selected_cred_id = raw.get("selected_cred_id")
    selected_host_id = raw.get("selected_host_id")
    selected_role_hosts = raw.get("selected_role_hosts") or {}
    encryption_enabled = bool(raw.get("encryption_enabled", os.environ.get("NIHIL_HISTORY_ENCRYPTION", "0") == "1"))
    return AppConfig(
        db_path=db_path,
        current_engagement=current_engagement,
        selected_cred_id=selected_cred_id,
        selected_host_id=selected_host_id,
        selected_role_hosts=selected_role_hosts,
        encryption_enabled=encryption_enabled,
    )


def save_config(config: AppConfig) -> None:
    cfg_path = config_path()
    payload = {
        "db_path": str(config.db_path),
        "current_engagement": config.current_engagement,
        "selected_cred_id": config.selected_cred_id,
        "selected_host_id": config.selected_host_id,
        "selected_role_hosts": config.selected_role_hosts,
        "encryption_enabled": config.encryption_enabled,
    }
    try:
        cfg_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except PermissionError:
        fallback_cfg = _fallback_home() / "config.json"
        fallback_cfg.parent.mkdir(parents=True, exist_ok=True)
        fallback_cfg.write_text(json.dumps(payload, indent=2), encoding="utf-8")
