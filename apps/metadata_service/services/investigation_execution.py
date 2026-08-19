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
    InvestigationReportCreate,
)
from apps.metadata_service.services.investigation_reports import (
    create_investigation_report,
    mark_investigation_job_failed,
    start_investigation_job,
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
) -> InvestigationReport:
    async with session_factory() as session:
        await start_investigation_job(
            session=session,
            job_id=job_id,
        )

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
    except Exception as exc:
        detail = str(exc).strip()
        error_message = exc.__class__.__name__

        if detail:
            error_message = f"{error_message}: {detail}"

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
    )

    async with session_factory() as session:
        return await create_investigation_report(
            session,
            request,
        )
