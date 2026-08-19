import argparse
import asyncio

from apps.metadata_service.config import get_settings
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.openai_client import (
    create_openai_client,
)
from apps.metadata_service.services.openai_embedding import (
    OpenAIEmbeddingProvider,
)
from apps.metadata_service.services.retriever_factory import (
    create_runbook_retriever,
)
from apps.metadata_service.services.runbook_loader import (
    load_runbooks,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Retrieve relevant runbook sections "
            "for an incident"
        )
    )

    parser.add_argument(
        "incident_id",
        help="Incident ID such as INC-DB-001",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum number of sections to retrieve",
    )

    return parser.parse_args()


async def retrieve_runbooks(
    incident_id: str,
    limit: int,
) -> None:
    settings = get_settings()
    incidents = load_incidents()

    if incident_id not in incidents:
        available_incidents = ", ".join(
            sorted(incidents)
        )

        raise ValueError(
            f"Unknown incident ID: {incident_id}. "
            f"Available incidents: {available_incidents}"
        )

    client = create_openai_client(settings)

    try:
        embedding_provider = OpenAIEmbeddingProvider(
            client=client,
            model=settings.openai_embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        retriever = await create_runbook_retriever(
            settings=settings,
            embedding_provider=embedding_provider,
            sections=load_runbooks(),
        )
        results = await retriever.retrieve(
            incident=incidents[incident_id],
            limit=limit,
        )
    finally:
        await client.close()

    print(f"Incident: {incident_id}")
    print(
        f"Embedding model: "
        f"{settings.openai_embedding_model}"
    )
    print(
        f"Retrieval backend: "
        f"{settings.retrieval_backend}"
    )
    print("Retrieved sections:")

    for rank, result in enumerate(results, start=1):
        section = result.section

        print(
            f"{rank}. {section.citation_id} "
            f"score={result.score:.4f}"
        )
        print(
            f"   {section.runbook_title} "
            f"— {section.section_title}"
        )


def main() -> None:
    arguments = parse_arguments()

    asyncio.run(
        retrieve_runbooks(
            incident_id=arguments.incident_id,
            limit=arguments.limit,
        )
    )


if __name__ == "__main__":
    main()
