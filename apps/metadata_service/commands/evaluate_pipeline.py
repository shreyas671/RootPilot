import argparse
import asyncio
from pathlib import Path

from openai import AsyncOpenAI

from apps.metadata_service.config import get_settings
from apps.metadata_service.services.evaluation import (
    run_pipeline_evaluation,
)
from apps.metadata_service.services.evaluation_loader import (
    DEFAULT_EVALUATION_DATASET,
    load_evaluation_dataset,
)
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.openai_analyst import (
    OpenAIIncidentAnalyst,
)
from apps.metadata_service.services.openai_embedding import (
    OpenAIEmbeddingProvider,
)
from apps.metadata_service.services.retriever import (
    InMemoryRunbookRetriever,
)
from apps.metadata_service.services.runbook_loader import (
    load_runbooks,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate RootPilot retrieval and structured "
            "incident assessments"
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_EVALUATION_DATASET,
        help="Path to an evaluation dataset JSON file",
    )

    return parser.parse_args()


async def evaluate_pipeline(dataset_path: Path) -> None:
    settings = get_settings()
    dataset = load_evaluation_dataset(dataset_path)
    incidents = load_incidents()
    client = AsyncOpenAI(
        api_key=(
            settings.openai_api_key.get_secret_value()
        )
    )

    try:
        embedding_provider = OpenAIEmbeddingProvider(
            client=client,
            model=settings.openai_embedding_model,
        )
        retriever = await InMemoryRunbookRetriever.create(
            embedding_provider=embedding_provider,
            sections=load_runbooks(),
        )
        analyst = OpenAIIncidentAnalyst(
            client=client,
            model=settings.openai_analysis_model,
        )
        summary = await run_pipeline_evaluation(
            dataset=dataset,
            incidents=incidents,
            retriever=retriever,
            analyst=analyst,
        )

        print(summary.model_dump_json(indent=2))
    finally:
        await client.close()


def main() -> None:
    arguments = parse_arguments()

    asyncio.run(
        evaluate_pipeline(arguments.dataset)
    )


if __name__ == "__main__":
    main()
