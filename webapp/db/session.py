"""Async SQLAlchemy session and engine helpers."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Awaitable, Callable, TypeVar

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from webapp.config import get_database_url
from .models import Base

T = TypeVar("T")

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return a singleton async engine instance."""
    global _engine, _sessionmaker
    if _engine is None:
        database_url = get_database_url()
        _engine = create_async_engine(database_url, echo=False, future=True)
        _sessionmaker = async_sessionmaker(
            bind=_engine,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return an async session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None  # for mypy
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional scope for database operations."""
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def run_in_session(func: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Execute an async callable inside a managed session."""
    async with session_scope() as session:
        return await func(session)


# Backwards compatible alias for historical imports
run_in_session_async = run_in_session


async def init_db() -> None:
    """Create database tables for the configured engine."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a session without automatically committing."""
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        yield session
