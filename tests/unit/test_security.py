from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from pydantic import SecretStr, ValidationError

from apps.metadata_service.config import Settings
from apps.metadata_service.security import (
    Principal,
    Role,
    decode_principal,
    require_roles,
)


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "postgres_user": "rootpilot",
        "postgres_password": "rootpilot",
        "postgres_db": "rootpilot",
        "postgres_host": "localhost",
        "postgres_port": 5432,
        "openai_api_key": "test-key",
        "auth_enabled": True,
        "auth_jwt_secret": "x" * 32,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_decode_principal_accepts_valid_token() -> None:
    settings = make_settings()
    token = jwt.encode(
        {
            "sub": "operator@example.com",
            "roles": ["operator"],
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.auth_jwt_secret.get_secret_value(),
        algorithm="HS256",
    )

    principal = decode_principal(token, settings)

    assert principal.subject == "operator@example.com"
    assert principal.roles == frozenset({Role.OPERATOR})


def test_decode_principal_rejects_expired_token() -> None:
    settings = make_settings()
    token = jwt.encode(
        {
            "sub": "operator@example.com",
            "roles": ["operator"],
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.auth_jwt_secret.get_secret_value(),
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as error:
        decode_principal(token, settings)

    assert error.value.status_code == 401


@pytest.mark.anyio
async def test_operator_inherits_viewer_permission() -> None:
    authorize = require_roles(Role.VIEWER)
    principal = Principal(
        subject="operator@example.com",
        roles=frozenset({Role.OPERATOR}),
    )

    assert await authorize(principal) == principal


@pytest.mark.anyio
async def test_viewer_cannot_use_operator_permission() -> None:
    authorize = require_roles(Role.OPERATOR)
    principal = Principal(
        subject="viewer@example.com",
        roles=frozenset({Role.VIEWER}),
    )

    with pytest.raises(HTTPException) as error:
        await authorize(principal)

    assert error.value.status_code == 403


def test_production_settings_require_secure_topology() -> None:
    with pytest.raises(
        ValidationError,
        match="AUTH_ENABLED must be true",
    ):
        make_settings(
            environment="production",
            auth_enabled=False,
        )

    settings = make_settings(
        environment="production",
        retrieval_backend="postgres",
        allowed_hosts=["api.rootpilot.example"],
        auth_jwt_secret=SecretStr("y" * 32),
    )

    assert settings.environment == "production"
