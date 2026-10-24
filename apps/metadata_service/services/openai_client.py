from openai import AsyncOpenAI

from apps.metadata_service.config import Settings


def create_openai_client(
    settings: Settings,
) -> AsyncOpenAI:
    client_options: dict[str, object] = {}
    if settings.openai_base_url is not None:
        client_options["base_url"] = settings.openai_base_url

    return AsyncOpenAI(
        api_key=(
            settings.openai_api_key.get_secret_value()
        ),
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
        **client_options,
    )
