import argparse
import asyncio

from openai import AsyncOpenAI

from apps.metadata_service.config import get_settings
from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.investigation_graph import (
    build_investigation_graph,
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


def positive_integer(value: str) -> int:
    parsed_value = int(value)

    if parsed_value < 1:
        raise argparse.ArgumentTypeError(
            "value must be at least 1"
        )

    return parsed_value


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Investigate an incident using retrieved "
            "runbook evidence"
        )
    )

    parser.add_argument(
        "incident_id",
        help="Incident ID such as INC-DB-001",
    )
    parser.add_argument(
        "--limit",
        type=positive_integer,
        default=3,
        help="Maximum number of runbook sections to retrieve",
    )

    return parser.parse_args()


def format_investigation_result(
    incident_id: str,
    embedding_model: str,
    analysis_model: str,
    retrieved_sections: list[
        RetrievedRunbookSection
    ],
    assessment: IncidentAssessment,
) -> str:
    lines = [
        f"Incident: {incident_id}",
        f"Embedding model: {embedding_model}",
        f"Analysis model: {analysis_model}",
        "",
        "Retrieved runbook sections:",
    ]

    for rank, result in enumerate(
        retrieved_sections,
        start=1,
    ):
        section = result.section

        lines.extend(
            [
                (
                    f"{rank}. {section.citation_id} "
                    f"score={result.score:.4f}"
                ),
                (
                    f"   {section.runbook_title} "
                    f"— {section.section_title}"
                ),
            ]
        )

    lines.extend(
        [
            "",
            "Incident assessment:",
            f"Root cause: {assessment.root_cause}",
            (
                "Confidence: "
                f"{assessment.confidence:.2f}"
            ),
            "",
            "Supporting evidence:",
        ]
    )

    lines.extend(
        f"- {evidence}"
        for evidence in assessment.supporting_evidence
    )

    lines.extend(
        [
            "",
            "Recommended actions:",
        ]
    )

    lines.extend(
        f"- {action}"
        for action in assessment.recommended_actions
    )

    lines.extend(
        [
            "",
            "Verification steps:",
        ]
    )

    lines.extend(
        f"- {step}"
        for step in assessment.verification_steps
    )

    lines.extend(
        [
            "",
            "Citations:",
        ]
    )

    lines.extend(
        f"- {citation_id}"
        for citation_id in assessment.citation_ids
    )

    return "\n".join(lines)


async def investigate_incident(
    incident_id: str,
    retrieval_limit: int,
) -> None:
    if retrieval_limit < 1:
        raise ValueError(
            "Retrieval limit must be at least 1"
        )

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

    incident = incidents[incident_id]

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

        graph = build_investigation_graph(
            retriever=retriever,
            analyst=analyst,
            retrieval_limit=retrieval_limit,
        )

        result = await graph.ainvoke(
            {
                "incident": incident,
            }
        )

        if result["assessment_validated"] is not True:
            raise ValueError(
                "Incident assessment was not validated"
            )

        output = format_investigation_result(
            incident_id=incident_id,
            embedding_model=(
                settings.openai_embedding_model
            ),
            analysis_model=(
                settings.openai_analysis_model
            ),
            retrieved_sections=(
                result["retrieved_sections"]
            ),
            assessment=result["assessment"],
        )

        print(output)
    finally:
        await client.close()


def main() -> None:
    arguments = parse_arguments()

    asyncio.run(
        investigate_incident(
            incident_id=arguments.incident_id,
            retrieval_limit=arguments.limit,
        )
    )


if __name__ == "__main__":
    main()