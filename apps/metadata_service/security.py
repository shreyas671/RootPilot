from enum import StrEnum
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from pydantic import BaseModel, ConfigDict

from apps.metadata_service.config import (
    Settings,
    get_settings,
)


class Role(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    roles: frozenset[Role]


bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _parse_roles(raw_roles: object) -> frozenset[Role]:
    if isinstance(raw_roles, str):
        values = raw_roles.split()
    elif isinstance(raw_roles, list):
        values = raw_roles
    else:
        values = []

    try:
        roles = frozenset(Role(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise _unauthorized(
            "Token contains invalid roles"
        ) from exc

    if not roles:
        raise _unauthorized(
            "Token must contain at least one role"
        )

    return roles


def decode_principal(
    token: str,
    settings: Settings,
) -> Principal:
    if settings.auth_jwt_secret is None:
        raise _unauthorized(
            "Authentication is not configured"
        )

    decode_options: dict[str, object] = {
        "algorithms": [settings.auth_jwt_algorithm],
    }

    if settings.auth_jwt_issuer is not None:
        decode_options["issuer"] = (
            settings.auth_jwt_issuer
        )

    if settings.auth_jwt_audience is not None:
        decode_options["audience"] = (
            settings.auth_jwt_audience
        )
    else:
        decode_options["options"] = {
            "verify_aud": False,
        }

    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret.get_secret_value(),
            **decode_options,
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized(
            "Invalid or expired bearer token"
        ) from exc

    subject = payload.get("sub")

    if not isinstance(subject, str) or not subject.strip():
        raise _unauthorized(
            "Token must contain a subject"
        )

    return Principal(
        subject=subject,
        roles=_parse_roles(payload.get("roles")),
    )


async def get_current_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> Principal:
    settings = get_settings()

    if not settings.auth_enabled:
        return Principal(
            subject="local-development",
            roles=frozenset({Role.ADMIN}),
        )

    if credentials is None:
        raise _unauthorized(
            "Bearer token is required"
        )

    return decode_principal(
        credentials.credentials,
        settings,
    )


def require_roles(
    *allowed_roles: Role,
) -> object:
    async def authorize(
        principal: Annotated[
            Principal,
            Depends(get_current_principal),
        ],
    ) -> Principal:
        effective_roles = set(principal.roles)

        if Role.ADMIN in effective_roles:
            effective_roles.update(Role)
        elif Role.OPERATOR in effective_roles:
            effective_roles.add(Role.VIEWER)

        if not effective_roles.intersection(
            allowed_roles
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )

        return principal

    return authorize
