from openai import AsyncOpenAI

from apps.metadata_service.config import Settings


def create_openai_client(
    settings: Settings,
) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=(
            settings.openai_api_key.get_secret_value()
        ),
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
