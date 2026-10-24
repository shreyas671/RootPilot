from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from apps.metadata_service.config import get_settings


@lru_cache
def get_database_url() -> URL:
    settings = get_settings()

    if settings.database_url is not None:
        database_url = make_url(
            settings.database_url.get_secret_value(),
        )
        if database_url.drivername in {
            "postgres",
            "postgresql",
        }:
            database_url = database_url.set(
                drivername="postgresql+asyncpg",
            )
        elif database_url.drivername != "postgresql+asyncpg":
            raise ValueError(
                "DATABASE_URL must use a PostgreSQL scheme"
            )

        # Hosted PostgreSQL providers commonly return libpq-style
        # parameters. SQLAlchemy forwards URL query parameters to
        # asyncpg, which expects `ssl` instead of `sslmode` and does
        # not accept `channel_binding`.
        query = dict(database_url.query)
        ssl_mode = query.pop("sslmode", None)
        query.pop("channel_binding", None)
        if ssl_mode is not None:
            query["ssl"] = ssl_mode

        database_url = database_url.set(query=query)
        return database_url

    if (
        settings.postgres_user is None
        or settings.postgres_password is None
        or settings.postgres_db is None
        or settings.postgres_host is None
        or settings.postgres_port is None
    ):
        raise RuntimeError(
            "PostgreSQL connection settings were not validated"
        )

    return URL.create(
        drivername="postgresql+asyncpg",
        username=settings.postgres_user,
        password=(
            settings.postgres_password.get_secret_value()
        ),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )

@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()

    engine_options: dict[str, object] = {
        "pool_pre_ping": True,
        "connect_args": {"timeout": 5},
    }

    if settings.environment == "test":
        engine_options["poolclass"] = NullPool
    else:
        engine_options.update(
            {
                "pool_size": settings.database_pool_size,
                "max_overflow": (
                    settings.database_max_overflow
                ),
                "pool_timeout": (
                    settings.database_pool_timeout_seconds
                ),
                "pool_recycle": (
                    settings.database_pool_recycle_seconds
                ),
            }
        )

    engine = create_async_engine(
        get_database_url(),
        **engine_options,
    )

    return engine


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
