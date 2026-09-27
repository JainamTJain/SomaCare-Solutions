"""Database session. SQLite for local runs and tests; PostgreSQL in Docker."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from turnwise.paths import data_dir

DEFAULT_SQLITE = data_dir() / "turnwise.db"


def database_url() -> str:
    return os.environ.get("TURNWISE_DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE}")


def _engine(url: str):
    if url.startswith("sqlite"):
        path = url.removeprefix("sqlite:///")
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


ENGINE = None
SessionLocal = None


def init_engine(url: str | None = None):
    global ENGINE, SessionLocal
    url = url or database_url()
    ENGINE = _engine(url)
    SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, expire_on_commit=False)
    return ENGINE


def get_session():
    if SessionLocal is None:
        init_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
