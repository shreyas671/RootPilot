from datetime import UTC, datetime

import jwt
import pytest

from apps.metadata_service.commands.create_access_token import (
    build_access_token,
)


def test_build_access_token_creates_expected_claims() -> None:
    secret = "x" * 32

    token = build_access_token(
        secret=secret,
        subject="operator@example.com",
        roles=["operator"],
        ttl_minutes=15,
        issuer="rootpilot-render",
        audience="rootpilot-api",
    )

    claims = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="rootpilot-render",
        audience="rootpilot-api",
    )
    assert claims["sub"] == "operator@example.com"
    assert claims["roles"] == ["operator"]
    assert datetime.fromtimestamp(
        claims["exp"],
        tz=UTC,
    ) > datetime.now(UTC)


def test_build_access_token_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="at least 32"):
        build_access_token(
            secret="short",
            subject="operator@example.com",
            roles=["operator"],
            ttl_minutes=15,
        )

    with pytest.raises(ValueError, match="subject"):
        build_access_token(
            secret="x" * 32,
            subject=" ",
            roles=["operator"],
            ttl_minutes=15,
        )

    with pytest.raises(ValueError, match="lifetime"):
        build_access_token(
            secret="x" * 32,
            subject="operator@example.com",
            roles=["operator"],
            ttl_minutes=0,
        )
