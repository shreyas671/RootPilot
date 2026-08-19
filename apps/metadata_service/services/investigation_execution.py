from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.metadata_service.models.investigation_report import (
    InvestigationReport,
)
from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)
from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.investigation import (
    InvestigationState,
)
from apps.metadata_service.schemas.investigation_report import (
    InvestigationProvenance,
    InvestigationReportCreate,
    RetrievedSectionTrace,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.investigation_reports import (
    create_investigation_report,
    mark_investigation_job_failed,
    start_investigation_job,
)
from apps.metadata_service.services.postgres_retriever import (
    runbook_content_hash,
)

SessionFactory = Callable[
    [],
    AbstractAsyncContextManager[AsyncSession],
]


class InvestigationWorkflow(Protocol):
    async def ainvoke(
        self,
        input: dict[str, IncidentEvidence],
    ) -> InvestigationState:
        ...


class InvalidInvestigationResultError(ValueError):
    pass


async def execute_and_persist_investigation(
    job_id: UUID,
    incident: IncidentEvidence,
    workflow: InvestigationWorkflow,
    session_factory: SessionFactory,
    embedding_model: str = "unknown",
    analysis_model: str = "unknown",
    prompt_version: str = "unknown",
    retrieval_backend: str = "memory",
    retrieval_limit: int = 3,
    minimum_relevance_score: float = 0.0,
) -> InvestigationReport:
    async with session_factory() as session:
        await start_investigation_job(
            session=session,
            job_id=job_id,
        )

    return await execute_claimed_and_persist_investigation(
        job_id=job_id,
        incident=incident,
        workflow=workflow,
        session_factory=session_factory,
        embedding_model=embedding_model,
        analysis_model=analysis_model,
        prompt_version=prompt_version,
        retrieval_backend=retrieval_backend,
        retrieval_limit=retrieval_limit,
        minimum_relevance_score=(
            minimum_relevance_score
        ),
    )


async def execute_claimed_and_persist_investigation(
    job_id: UUID,
    incident: IncidentEvidence,
    workflow: InvestigationWorkflow,
    session_factory: SessionFactory,
    embedding_model: str = "unknown",
    analysis_model: str = "unknown",
    prompt_version: str = "unknown",
    retrieval_backend: str = "memory",
    retrieval_limit: int = 3,
    minimum_relevance_score: float = 0.0,
    mark_failure: bool = True,
) -> InvestigationReport:

    try:
        result = await workflow.ainvoke(
            {
                "incident": incident,
            }
        )

        if result.get("assessment_validated") is not True:
            raise InvalidInvestigationResultError(
                "Incident assessment was not validated"
            )

        assessment = result.get("assessment")

        if not isinstance(
            assessment,
            IncidentAssessment,
        ):
            raise InvalidInvestigationResultError(
                "Investigation did not produce an assessment"
            )
        retrieved_sections = result.get(
            "retrieved_sections",
            [],
        )
        traces = []

        for retrieved in retrieved_sections:
            if not isinstance(
                retrieved,
                RetrievedRunbookSection,
            ):
                raise InvalidInvestigationResultError(
                    "Investigation returned invalid retrieval "
                    "provenance"
                )

            traces.append(
                RetrievedSectionTrace(
                    citation_id=(
                        retrieved.section.citation_id
                    ),
                    score=retrieved.score,
                    content_hash=runbook_content_hash(
                        retrieved.section
                    ),
                    source_file=(
                        retrieved.section.source_file
                    ),
                )
            )
    except Exception as exc:
        detail = str(exc).strip()
        error_message = exc.__class__.__name__

        if detail:
            error_message = f"{error_message}: {detail}"

        if mark_failure:
            async with session_factory() as session:
                await mark_investigation_job_failed(
                    session=session,
                    job_id=job_id,
                    error_message=error_message,
                )

        raise

    request = InvestigationReportCreate(
        job_id=job_id,
        assessment=assessment,
        provenance=InvestigationProvenance(
            embedding_model=embedding_model,
            analysis_model=analysis_model,
            prompt_version=prompt_version,
            retrieval_backend=retrieval_backend,
            retrieval_limit=retrieval_limit,
            minimum_relevance_score=(
                minimum_relevance_score
            ),
            retrieved_sections=traces,
        ),
    )

    async with session_factory() as session:
        return await create_investigation_report(
            session,
            request,
        )
