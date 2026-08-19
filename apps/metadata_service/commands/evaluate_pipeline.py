import argparse
import asyncio
from pathlib import Path

from apps.metadata_service.config import get_settings
from apps.metadata_service.schemas.evaluation import (
    PipelineEvaluationSummary,
)
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


def unit_interval(value: str) -> float:
    parsed = float(value)

    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError(
            "value must be between 0.0 and 1.0"
        )

    return parsed


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
    parser.add_argument(
        "--minimum-retrieval-pass-rate",
        type=unit_interval,
        default=1.0,
        help="Fail when retrieval pass rate is below this value",
    )
    parser.add_argument(
        "--minimum-assessment-pass-rate",
        type=unit_interval,
        default=1.0,
        help="Fail when assessment pass rate is below this value",
    )

    return parser.parse_args()


async def evaluate_pipeline(
    dataset_path: Path,
) -> PipelineEvaluationSummary:
    settings = get_settings()
    dataset = load_evaluation_dataset(dataset_path)
    incidents = load_incidents()
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
        return summary
    finally:
        await client.close()


def main() -> None:
    arguments = parse_arguments()

    summary = asyncio.run(
        evaluate_pipeline(arguments.dataset)
    )

    if (
        summary.retrieval.pass_rate
        < arguments.minimum_retrieval_pass_rate
        or summary.assessment.pass_rate
        < arguments.minimum_assessment_pass_rate
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
