import argparse
import asyncio
from uuid import UUID

from apps.metadata_service.config import get_settings
from apps.metadata_service.database import get_session_factory
from apps.metadata_service.models.investigation_report import (
    InvestigationReport,
)
from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.investigation_execution import (
    execute_and_persist_investigation,
)
from apps.metadata_service.services.investigation_graph import (
    build_investigation_graph,
)
from apps.metadata_service.services.openai_analyst import (
    INCIDENT_ANALYST_PROMPT_VERSION,
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


def positive_integer(value: str) -> int:
    parsed_value = int(value)

    if parsed_value < 1:
        raise argparse.ArgumentTypeError(
            "value must be at least 1"
        )

    return parsed_value


def relevance_score(value: str) -> float:
    parsed_value = float(value)

    if not -1.0 <= parsed_value <= 1.0:
        raise argparse.ArgumentTypeError(
            "value must be between -1.0 and 1.0"
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
        "--job-id",
        type=UUID,
        default=None,
        help=(
            "Pending job UUID used to persist "
            "the investigation report"
        ),
    )
    parser.add_argument(
        "--limit",
        type=positive_integer,
        default=3,
        help="Maximum number of runbook sections to retrieve",
    )
    parser.add_argument(
        "--minimum-score",
        type=relevance_score,
        default=0.0,
        help=(
            "Minimum cosine-similarity score required "
            "for runbook evidence"
        ),
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


def format_persisted_investigation_result(
    report: InvestigationReport,
    embedding_model: str,
    analysis_model: str,
) -> str:
    lines = [
        f"Report ID: {report.id}",
        f"Job ID: {report.job_id}",
        f"Incident: {report.incident_id}",
        f"Review status: {report.status.value}",
        f"Embedding model: {embedding_model}",
        f"Analysis model: {analysis_model}",
        "",
        "Incident assessment:",
        f"Root cause: {report.root_cause}",
        f"Confidence: {report.confidence:.2f}",
        "",
        "Citations:",
    ]

    lines.extend(
        f"- {citation_id}"
        for citation_id in report.citation_ids
    )

    return "\n".join(lines)


async def investigate_incident(
    incident_id: str,
    retrieval_limit: int,
    job_id: UUID | None = None,
    minimum_relevance_score: float = 0.0,
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

        graph = build_investigation_graph(
            retriever=retriever,
            analyst=analyst,
            retrieval_limit=retrieval_limit,
            minimum_relevance_score=(
                minimum_relevance_score
            ),
        )

        if job_id is not None:
            report = (
                await execute_and_persist_investigation(
                    job_id=job_id,
                    incident=incident,
                    workflow=graph,
                    session_factory=(
                        get_session_factory()
                    ),
                    embedding_model=(
                        settings.openai_embedding_model
                    ),
                    analysis_model=(
                        settings.openai_analysis_model
                    ),
                    prompt_version=(
                        INCIDENT_ANALYST_PROMPT_VERSION
                    ),
                    retrieval_backend=(
                        settings.retrieval_backend
                    ),
                    retrieval_limit=retrieval_limit,
                    minimum_relevance_score=(
                        minimum_relevance_score
                    ),
                )
            )

            output = (
                format_persisted_investigation_result(
                    report=report,
                    embedding_model=(
                        settings.openai_embedding_model
                    ),
                    analysis_model=(
                        settings.openai_analysis_model
                    ),
                )
            )

            print(output)
            return

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
            job_id=arguments.job_id,
            minimum_relevance_score=(
                arguments.minimum_score
            ),
        )
    )


if __name__ == "__main__":
    main()
