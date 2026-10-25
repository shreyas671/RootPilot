import asyncio

from apps.metadata_service.config import Settings
from apps.metadata_service.services import openai_client
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
                "https://private-gateway.example/v1"
            )
        )
    )

    assert str(client.base_url) == (
        "https://private-gateway.example/v1/"
    )


def test_settings_accept_compatible_gateway_model_aliases(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "BULLSAI_EMBED_MODEL",
        "embedding-model-test",
    )
    monkeypatch.setenv(
        "OPENAI_MODEL",
        "analysis-model-test",
    )

    settings = make_settings()

    assert settings.openai_embedding_model == (
        "embedding-model-test"
    )
    assert settings.openai_analysis_model == (
        "analysis-model-test"
    )


def test_create_openai_client_adds_langsmith_wrapper(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_wrap_openai(
        client: object,
        *,
        tracing_extra: dict[str, object],
    ) -> object:
        captured["client"] = client
        captured["tracing_extra"] = tracing_extra
        return client

    monkeypatch.setattr(
        openai_client,
        "wrap_openai",
        fake_wrap_openai,
    )

    client = create_openai_client(make_settings())

    assert captured["client"] is client
    assert captured["tracing_extra"] == {
        "tags": ["rootpilot", "development"],
        "metadata": {
            "service": "rootpilot-metadata-service",
            "environment": "development",
        },
    }

    asyncio.run(client.close())
