from __future__ import annotations

from pathlib import Path
from importlib import resources

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from nihil_history.config import ensure_home, load_config, save_config


def get_engine():
    cfg = load_config()
    return create_engine(f"sqlite:///{cfg.db_path}", future=True)


def init_db() -> None:
    cfg = load_config()
    migration_dir = resources.files("nihil_history").joinpath("alembic")

    def _run(db_path: Path) -> None:
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", str(migration_dir))
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        db_inspector = inspect(engine)
        has_alembic = db_inspector.has_table("alembic_version")
        has_legacy_schema = db_inspector.has_table("engagements")
        if has_legacy_schema and not has_alembic:
            # Existing DB created before Alembic adoption: mark it migrated.
            command.stamp(alembic_cfg, "head")
            return
        try:
            command.upgrade(alembic_cfg, "head")
        except OperationalError as exc:
            message = str(exc).lower()
            if "already exists" in message:
                # Safety net for legacy DBs not stamped yet.
                command.stamp(alembic_cfg, "head")
                return
            raise

    try:
        _run(cfg.db_path)
    except OperationalError as exc:
        message = str(exc).lower()
        if "readonly" in message:
            # Move to writable fallback when historical path is not writable.
            new_db = ensure_home() / "history.db"
            cfg.db_path = new_db
            save_config(cfg)
            _run(new_db)
            return
        raise


def get_session() -> Session:
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    return factory()
