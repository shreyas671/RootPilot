from functools import lru_cache
from typing import Literal, Self

from pydantic import (
    AliasChoices,
    Field,
    SecretStr,
    model_validator,
)
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

    database_url: SecretStr | None = None
    postgres_user: str | None = None
    postgres_password: SecretStr | None = None
    postgres_db: str | None = None
    postgres_host: str | None = None
    postgres_port: int | None = None
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout_seconds: float = 30.0
    database_pool_recycle_seconds: int = 1800

    openai_api_key: SecretStr
    openai_base_url: str | None = None
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        validation_alias=AliasChoices(
            "OPENAI_EMBEDDING_MODEL",
            "BULLSAI_EMBED_MODEL",
        ),
    )
    openai_analysis_model: str = Field(
        default="gpt-5.6-sol",
        validation_alias=AliasChoices(
            "OPENAI_ANALYSIS_MODEL",
            "OPENAI_MODEL",
        ),
    )
    openai_analysis_api: Literal[
        "responses",
        "chat_completions",
    ] = "responses"
    openai_timeout_seconds: float = 60.0
    openai_max_retries: int = 2

    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "rootpilot"
    langsmith_endpoint: str | None = None
    langsmith_workspace_id: str | None = None
    langsmith_hide_inputs: bool = False
    langsmith_hide_outputs: bool = False

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

    investigation_mode: Literal[
        "single_pass",
        "react",
    ] = "react"
    react_max_iterations: int = 8
    react_max_tool_calls: int = 10
    react_no_progress_limit: int = 2
    react_max_tool_errors: int = 3
    react_max_runtime_seconds: float = 180.0
    react_max_context_sections: int = 10
    react_min_evidence_items: int = 2
    react_max_repair_attempts: int = 2

    worker_poll_interval_seconds: float = 2.0
    worker_lease_seconds: int = 300
    worker_max_attempts: int = 3
    embedded_worker_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def validate_production_settings(self) -> Self:
        if self.database_url is None:
            database_components = {
                "POSTGRES_USER": self.postgres_user,
                "POSTGRES_PASSWORD": self.postgres_password,
                "POSTGRES_DB": self.postgres_db,
                "POSTGRES_HOST": self.postgres_host,
                "POSTGRES_PORT": self.postgres_port,
            }
            missing_components = [
                name
                for name, value in database_components.items()
                if value is None
            ]
            if missing_components:
                missing = ", ".join(missing_components)
                raise ValueError(
                    "DATABASE_URL or all PostgreSQL connection "
                    f"settings are required; missing: {missing}"
                )

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
            "REACT_MAX_ITERATIONS": (
                self.react_max_iterations
            ),
            "REACT_MAX_TOOL_CALLS": (
                self.react_max_tool_calls
            ),
            "REACT_NO_PROGRESS_LIMIT": (
                self.react_no_progress_limit
            ),
            "REACT_MAX_TOOL_ERRORS": (
                self.react_max_tool_errors
            ),
            "REACT_MAX_RUNTIME_SECONDS": (
                self.react_max_runtime_seconds
            ),
            "REACT_MAX_CONTEXT_SECTIONS": (
                self.react_max_context_sections
            ),
            "REACT_MIN_EVIDENCE_ITEMS": (
                self.react_min_evidence_items
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

        if self.react_max_repair_attempts < 0:
            raise ValueError(
                "REACT_MAX_REPAIR_ATTEMPTS cannot be negative"
            )

        if not self.langsmith_project.strip():
            raise ValueError(
                "LANGSMITH_PROJECT cannot be empty"
            )

        if (
            self.langsmith_tracing
            and self.langsmith_api_key is None
        ):
            raise ValueError(
                "LANGSMITH_API_KEY is required when "
                "LANGSMITH_TRACING is enabled"
            )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
