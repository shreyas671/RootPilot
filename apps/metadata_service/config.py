from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    environment: Literal[
        "development",
        "test",
        "production",
    ] = "development"
    log_level: str = "INFO"
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["*"],
    )
    cors_origins: list[str] = Field(default_factory=list)
    docs_enabled: bool = True

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str
    postgres_port: int
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout_seconds: float = 30.0
    database_pool_recycle_seconds: int = 1800

    openai_api_key: SecretStr
    openai_embedding_model: str = (
        "text-embedding-3-small"
    )
    openai_analysis_model: str = "gpt-5.6-sol"
    openai_timeout_seconds: float = 60.0
    openai_max_retries: int = 2

    auth_enabled: bool = False
    auth_jwt_secret: SecretStr | None = None
    auth_jwt_algorithm: Literal["HS256"] = "HS256"
    auth_jwt_issuer: str | None = None
    auth_jwt_audience: str | None = None

    retrieval_backend: Literal[
        "memory",
        "postgres",
    ] = "memory"
    embedding_dimensions: int = 1536
    default_retrieval_limit: int = 3
    default_minimum_relevance_score: float = 0.0

    worker_poll_interval_seconds: float = 2.0
    worker_lease_seconds: int = 300
    worker_max_attempts: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_settings(self) -> Self:
        if self.auth_enabled:
            if self.auth_jwt_secret is None:
                raise ValueError(
                    "AUTH_JWT_SECRET is required when "
                    "authentication is enabled"
                )

            if len(
                self.auth_jwt_secret.get_secret_value()
            ) < 32:
                raise ValueError(
                    "AUTH_JWT_SECRET must contain at least "
                    "32 characters"
                )

        if self.environment == "production":
            if not self.auth_enabled:
                raise ValueError(
                    "AUTH_ENABLED must be true in production"
                )

            if self.retrieval_backend != "postgres":
                raise ValueError(
                    "RETRIEVAL_BACKEND must be postgres "
                    "in production"
                )

            if "*" in self.allowed_hosts:
                raise ValueError(
                    "ALLOWED_HOSTS cannot contain '*' "
                    "in production"
                )

        if self.embedding_dimensions < 1:
            raise ValueError(
                "EMBEDDING_DIMENSIONS must be at least 1"
            )

        if not -1.0 <= (
            self.default_minimum_relevance_score
        ) <= 1.0:
            raise ValueError(
                "DEFAULT_MINIMUM_RELEVANCE_SCORE must be "
                "between -1.0 and 1.0"
            )

        positive_values = {
            "DATABASE_POOL_SIZE": self.database_pool_size,
            "DATABASE_POOL_TIMEOUT_SECONDS": (
                self.database_pool_timeout_seconds
            ),
            "DATABASE_POOL_RECYCLE_SECONDS": (
                self.database_pool_recycle_seconds
            ),
            "OPENAI_TIMEOUT_SECONDS": (
                self.openai_timeout_seconds
            ),
            "DEFAULT_RETRIEVAL_LIMIT": (
                self.default_retrieval_limit
            ),
            "WORKER_POLL_INTERVAL_SECONDS": (
                self.worker_poll_interval_seconds
            ),
            "WORKER_LEASE_SECONDS": self.worker_lease_seconds,
            "WORKER_MAX_ATTEMPTS": self.worker_max_attempts,
        }

        for name, value in positive_values.items():
            if value <= 0:
                raise ValueError(
                    f"{name} must be greater than zero"
                )

        if self.database_max_overflow < 0:
            raise ValueError(
                "DATABASE_MAX_OVERFLOW cannot be negative"
            )

        if self.openai_max_retries < 0:
            raise ValueError(
                "OPENAI_MAX_RETRIES cannot be negative"
            )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
