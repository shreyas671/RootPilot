import os
from uuid import uuid4

import pytest
from sqlalchemy import delete

from apps.metadata_service.database import (
    get_session_factory,
)
from apps.metadata_service.models.investigation_report import (
    InvestigationReport,
    InvestigationReportStatus,
)
from apps.metadata_service.models.job import Job, JobStatus
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
    InvestigationReportReview,
)
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.investigation_execution import (
    execute_and_persist_investigation,
)
from apps.metadata_service.services.investigation_reports import (
    list_investigation_review_events,
    review_investigation_report,
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
        reason=(
            "set RUN_POSTGRES_INTEGRATION=1 to run "
            "PostgreSQL integration tests"
        ),
    ),
]


class DeterministicWorkflow:
    def __init__(
        self,
        assessment: IncidentAssessment,
    ) -> None:
        self.assessment = assessment

    async def ainvoke(
        self,
        input: dict[str, IncidentEvidence],
    ) -> InvestigationState:
        return {
            "incident": input["incident"],
            "assessment": self.assessment,
            "assessment_validated": True,
        }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_persisted_investigation_review_flow() -> None:
    session_factory = get_session_factory()
    incident = load_incidents()["INC-DB-001"]
    assessment = IncidentAssessment(
        incident_id=incident.incident_id,
        root_cause="Database connection pool exhaustion",
        supporting_evidence=[
            "Connection usage reached the configured limit.",
        ],
        recommended_actions=[
            "Reduce idle connections and tune the pool.",
        ],
        verification_steps=[
            "Confirm connection utilization returns to normal.",
        ],
        confidence=0.93,
        citation_ids=[
            "RB-DB-001#connection-exhaustion",
        ],
    )
    job = Job(
        id=uuid4(),
        input_path=(
            "data/incidents/INC-DB-001.json"
        ),
        status=JobStatus.PENDING,
    )

    async with session_factory() as session:
        session.add(job)
        await session.commit()

    try:
        report = await execute_and_persist_investigation(
            job_id=job.id,
            incident=incident,
            workflow=DeterministicWorkflow(assessment),
            session_factory=session_factory,
        )

        assert report.status is (
            InvestigationReportStatus.PENDING_REVIEW
        )

        async with session_factory() as session:
            reviewed_report = (
                await review_investigation_report(
                    session=session,
                    report_id=report.id,
                    request=InvestigationReportReview(
                        status=(
                            InvestigationReportStatus.APPROVED
                        ),
                        reviewed_by="integration-test",
                        reviewer_feedback=(
                            "Evidence and citations verified."
                        ),
                    ),
                )
            )

        assert reviewed_report.status is (
            InvestigationReportStatus.APPROVED
        )

        async with session_factory() as session:
            persisted_job = await session.get(
                Job,
                job.id,
            )
            persisted_report = await session.get(
                InvestigationReport,
                report.id,
            )
            review_events = (
                await list_investigation_review_events(
                    session=session,
                    report_id=report.id,
                )
            )

        assert persisted_job is not None
        assert persisted_job.status is JobStatus.COMPLETED
        assert persisted_job.started_at is not None
        assert persisted_job.completed_at is not None
        assert persisted_report is not None
        assert persisted_report.status is (
            InvestigationReportStatus.APPROVED
        )
        assert len(review_events) == 1
        assert review_events[0].previous_status is (
            InvestigationReportStatus.PENDING_REVIEW
        )
        assert review_events[0].new_status is (
            InvestigationReportStatus.APPROVED
        )
        assert review_events[0].reviewed_by == (
            "integration-test"
        )
    finally:
        async with session_factory() as session:
            await session.execute(
                delete(Job).where(Job.id == job.id)
            )
            await session.commit()
