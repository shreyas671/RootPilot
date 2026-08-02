from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from apps.metadata_service.config import get_settings

@lru_cache
def get_database_url() -> URL:
    settings = get_settings()

    return URL.create(
        drivername="postgresql+asyncpg",
        username=settings.postgres_user,
        password=settings.postgres_password,
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )

@lru_cache
@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(
        get_database_url(),
        pool_pre_ping=True,
        connect_args={"timeout": 5},
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db_session() -> AsyncIterator[AsyncSession]:
    session_factory = get_session_factory()

    async with session_factory() as session:
        yield session