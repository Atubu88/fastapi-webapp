"""Async database utilities for the FastAPI web application."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Awaitable, Callable, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from webapp.config import get_database_url
from webapp.models import Base

T = TypeVar("T")

# ⚙️ Ленивое создание (lazy initialization)
_engine = None
_SessionLocal = None


def get_engine():
    """Create async engine only once (lazy)."""
    global _engine, _SessionLocal
    if _engine is None:
        DATABASE_URL = get_database_url()
        _engine = create_async_engine(DATABASE_URL, echo=False, future=True)
        _SessionLocal = async_sessionmaker(
            bind=_engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _engine, _SessionLocal


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Provide async transactional scope around operations."""
    engine, SessionLocal = get_engine()
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create tables if they do not exist (useful for testing)."""
    engine, _ = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def run_in_session(func: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Execute async callable inside DB session."""
    async with session_scope() as session:
        return await func(session)


# ✅ Backward compatibility alias
# Some older modules (e.g. supabase_client, match_service) still import this name.
run_in_session_async = run_in_session
