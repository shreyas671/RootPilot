import argparse
import os
from datetime import UTC, datetime, timedelta

import jwt


def build_access_token(
    *,
    secret: str,
    subject: str,
    roles: list[str],
    ttl_minutes: int,
    issuer: str | None = None,
    audience: str | None = None,
) -> str:
    if len(secret) < 32:
        raise ValueError(
            "AUTH_JWT_SECRET must contain at least 32 characters"
        )
    if not subject.strip():
        raise ValueError("Token subject cannot be empty")
    if ttl_minutes < 1:
        raise ValueError("Token lifetime must be at least one minute")

    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": subject.strip(),
        "roles": roles,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    if issuer:
        payload["iss"] = issuer
    if audience:
        payload["aud"] = audience

    return jwt.encode(payload, secret, algorithm="HS256")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a short-lived RootPilot dashboard access token "
            "using the service's AUTH_JWT_* environment variables."
        ),
    )
    parser.add_argument("--subject", required=True)
    parser.add_argument(
        "--role",
        action="append",
        choices=["viewer", "operator", "admin"],
        default=None,
        help=(
            "Role to grant. Repeat for multiple roles. "
            "Defaults to operator."
        ),
    )
    parser.add_argument(
        "--ttl-minutes",
        type=int,
        default=60,
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    secret = os.getenv("AUTH_JWT_SECRET")
    if secret is None:
        raise SystemExit("AUTH_JWT_SECRET is not set")

    try:
        token = build_access_token(
            secret=secret,
            subject=arguments.subject,
            roles=arguments.role or ["operator"],
            ttl_minutes=arguments.ttl_minutes,
            issuer=os.getenv("AUTH_JWT_ISSUER"),
            audience=os.getenv("AUTH_JWT_AUDIENCE"),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(token)


if __name__ == "__main__":
    main()
