from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker

from core.config import BASE_DIR


def _normalize_database_url(database_url: str) -> str:
    """Normalize the database URL for the sync SQLAlchemy engine."""

    try:
        sa_url = make_url(database_url)
    except ArgumentError:
        return database_url

    if sa_url.drivername.endswith("+asyncpg"):
        sa_url = sa_url.set(drivername=sa_url.drivername.replace("+asyncpg", "+psycopg2", 1))

    return str(sa_url)


def _build_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return _normalize_database_url(database_url)
    default_path = BASE_DIR / "app.db"
    return f"sqlite:///{default_path}"  # pragma: no cover - fallback для dev среды


DATABASE_URL = _build_database_url()

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine: Engine = create_engine(DATABASE_URL, future=True, connect_args=connect_args)

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
    future=True,
)


def get_session() -> Session:
    return SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = ["SessionLocal", "engine", "get_session", "session_scope"]
