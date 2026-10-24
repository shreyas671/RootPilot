from pydantic import SecretStr

from apps.metadata_service import database
from apps.metadata_service.config import Settings


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": None,
        "postgres_user": "rootpilot",
        "postgres_password": "database-password",
        "postgres_db": "rootpilot",
        "postgres_host": "localhost",
        "postgres_port": 5432,
        "openai_api_key": "test-key",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_get_database_url_uses_component_settings(
    monkeypatch,
) -> None:
    settings = make_settings()
    monkeypatch.setattr(
        database,
        "get_settings",
        lambda: settings,
    )
    database.get_database_url.cache_clear()

    url = database.get_database_url()

    assert url.drivername == "postgresql+asyncpg"
    assert url.username == "rootpilot"
    assert url.password == "database-password"
    assert url.host == "localhost"
    assert url.database == "rootpilot"
    database.get_database_url.cache_clear()


def test_get_database_url_accepts_render_connection_string(
    monkeypatch,
) -> None:
    settings = make_settings(
        database_url=SecretStr(
            "postgresql://render:secret@internal-db:5432/rootpilot"
        ),
        postgres_user=None,
        postgres_password=None,
        postgres_db=None,
        postgres_host=None,
        postgres_port=None,
    )
    monkeypatch.setattr(
        database,
        "get_settings",
        lambda: settings,
    )
    database.get_database_url.cache_clear()

    url = database.get_database_url()

    assert url.drivername == "postgresql+asyncpg"
    assert url.username == "render"
    assert url.password == "secret"
    assert url.host == "internal-db"
    assert url.database == "rootpilot"
    database.get_database_url.cache_clear()


def test_get_database_url_normalizes_neon_ssl_parameters(
    monkeypatch,
) -> None:
    settings = make_settings(
        database_url=SecretStr(
            "postgresql://neon:secret@ep-test.neon.tech/rootpilot"
            "?sslmode=require&channel_binding=require"
        ),
        postgres_user=None,
        postgres_password=None,
        postgres_db=None,
        postgres_host=None,
        postgres_port=None,
    )
    monkeypatch.setattr(
        database,
        "get_settings",
        lambda: settings,
    )
    database.get_database_url.cache_clear()

    url = database.get_database_url()

    assert url.drivername == "postgresql+asyncpg"
    assert dict(url.query) == {"ssl": "require"}
    database.get_database_url.cache_clear()
