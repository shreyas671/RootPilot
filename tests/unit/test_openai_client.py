from apps.metadata_service.config import Settings
from apps.metadata_service.services.openai_client import (
    create_openai_client,
)


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "postgres_user": "rootpilot",
        "postgres_password": "database-password",
        "postgres_db": "rootpilot",
        "postgres_host": "localhost",
        "postgres_port": 5432,
        "openai_api_key": "test-key",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_create_openai_client_uses_custom_base_url() -> None:
    client = create_openai_client(
        make_settings(
            openai_base_url=(
                "https://gateway.bullsai.buffalo.edu/v1"
            )
        )
    )

    assert str(client.base_url) == (
        "https://gateway.bullsai.buffalo.edu/v1/"
    )


def test_settings_accept_bullsai_model_aliases(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "BULLSAI_EMBED_MODEL",
        "BAAI/bge-m3",
    )
    monkeypatch.setenv(
        "OPENAI_MODEL",
        "openai/gpt-oss-20b",
    )

    settings = make_settings()

    assert settings.openai_embedding_model == "BAAI/bge-m3"
    assert settings.openai_analysis_model == (
        "openai/gpt-oss-20b"
    )
