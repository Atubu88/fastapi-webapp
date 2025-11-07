"""Database utilities for the FastAPI web application."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Callable, Generator, TypeVar

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from webapp.config import DATABASE_URL
from webapp.models import Base

_engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all database tables if they do not exist."""

    Base.metadata.create_all(bind=_engine)


T = TypeVar("T")


def run_in_session(func: Callable[[Session], T]) -> T:
    """Execute the given callable inside a database session."""

    with session_scope() as session:
        return func(session)


async def run_in_session_async(func: Callable[[Session], T]) -> T:
    """Async helper that delegates execution to a thread pool."""

    return await asyncio.to_thread(run_in_session, func)
