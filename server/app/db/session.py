"""Engine e sessões assíncronas (SQLAlchemy 2 + psycopg 3)."""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine | None:
    url = get_settings().database_url
    if not url:
        return None
    return create_async_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL não configurada")
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def check_db(engine: AsyncEngine | None) -> str:
    """'ok' | 'error' | 'not_configured'. Nunca levanta exceção."""
    if engine is None:
        return "not_configured"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"
