from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI

from apps.metadata_service.config import Settings
from apps.metadata_service.observability import (
    configure_langsmith_tracing,
)


def create_openai_client(
    settings: Settings,
) -> AsyncOpenAI:
    configure_langsmith_tracing(settings)
    client_options: dict[str, object] = {}
    if settings.openai_base_url is not None:
        client_options["base_url"] = settings.openai_base_url

    client = AsyncOpenAI(
        api_key=(
            settings.openai_api_key.get_secret_value()
        ),
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
        **client_options,
    )

    return wrap_openai(
        client,
        tracing_extra={
            "tags": [
                "rootpilot",
                settings.environment,
            ],
            "metadata": {
                "service": "rootpilot-metadata-service",
                "environment": settings.environment,
            },
        },
    )
