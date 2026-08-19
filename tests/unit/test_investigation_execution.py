from datetime import UTC, datetime
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

import pytest

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
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.investigation_execution import (
    InvalidInvestigationResultError,
    execute_and_persist_investigation,
)


class FakeWorkflow:
    def __init__(
        self,
        result: InvestigationState,
        events: list[str],
    ) -> None:
        self.result = result
        self.events = events
        self.inputs: list[str] = []

    async def ainvoke(
        self,
        input: dict[str, IncidentEvidence],
    ) -> InvestigationState:
        self.events.append("workflow")
        self.inputs.append(
            input["incident"].incident_id
        )

        return self.result


class FakeSession:
    def __init__(
        self,
        job: Job,
        events: list[str],
    ) -> None:
        self.job = job
        self.events = events
        self.added_report: (
            InvestigationReport | None
        ) = None
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> Self:
        self.events.append("session_enter")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.events.append("session_exit")

    async def get(
        self,
        model: type[Job],
        job_id: UUID,
        *,
        with_for_update: bool = False,
    ) -> Job | None:
        self.events.append("database_get")

        assert model is Job
        assert with_for_update is True

        if self.job.id != job_id:
            return None

        return self.job

    def add(
        self,
        report: InvestigationReport,
    ) -> None:
        self.events.append("database_add")
        self.added_report = report

    async def flush(self) -> None:
        now = datetime.now(UTC)

        if self.added_report is not None:
            self.added_report.id = uuid4()
            self.added_report.created_at = now
            self.added_report.updated_at = now

        self.job.updated_at = now

    async def refresh(
        self,
        report: InvestigationReport,
    ) -> None:
        assert report is self.added_report

    async def commit(self) -> None:
        self.committed = True
        self.rolled_back = False

    async def rollback(self) -> None:
        self.committed = False
        self.rolled_back = True


class FakeSessionFactory:
    def __init__(
        self,
        session: FakeSession,
        events: list[str],
    ) -> None:
        self.session = session
        self.events = events
        self.calls = 0

    def __call__(self) -> FakeSession:
        self.calls += 1
        self.events.append("session_created")

        return self.session


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def make_assessment() -> IncidentAssessment:
    return IncidentAssessment(
        incident_id="INC-DB-001",
        root_cause="Database connection exhaustion",
        supporting_evidence=[
            "Connection usage reached its maximum.",
        ],
        recommended_actions=[
            "Reduce idle database connections.",
        ],
        verification_steps=[
            "Verify connection usage returns to normal.",
        ],
        confidence=0.92,
        citation_ids=[
            "RB-DB-001#diagnosis",
        ],
    )


def make_pending_job() -> Job:
    now = datetime.now(UTC)

    return Job(
        id=uuid4(),
        input_path="data/incidents/INC-DB-001.json",
        status=JobStatus.PENDING,
        error_message=None,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.anyio
async def test_execution_persists_validated_assessment() -> None:
    events: list[str] = []
    incident = load_incidents()["INC-DB-001"]
    assessment = make_assessment()
    job = make_pending_job()

    workflow = FakeWorkflow(
        result={
            "incident": incident,
            "assessment": assessment,
            "assessment_validated": True,
        },
        events=events,
    )

    session = FakeSession(
        job=job,
        events=events,
    )
    session_factory = FakeSessionFactory(
        session=session,
        events=events,
    )

    report = await execute_and_persist_investigation(
        job_id=job.id,
        incident=incident,
        workflow=workflow,
        session_factory=session_factory,
    )

    assert report is session.added_report
    assert report.incident_id == "INC-DB-001"
    assert report.status is (
        InvestigationReportStatus.PENDING_REVIEW
    )
    assert job.status is JobStatus.COMPLETED
    assert job.started_at is not None
    assert session.committed is True

    workflow_index = events.index("workflow")
    session_exit_index = events.index("session_exit")
    database_get_indexes = [
        index
        for index, event in enumerate(events)
        if event == "database_get"
    ]

    assert session_exit_index < workflow_index
    assert workflow_index < database_get_indexes[1]
    assert session_factory.calls == 2


@pytest.mark.anyio
async def test_execution_rejects_unvalidated_result() -> None:
    events: list[str] = []
    incident = load_incidents()["INC-DB-001"]
    job = make_pending_job()

    workflow = FakeWorkflow(
        result={
            "incident": incident,
            "assessment": make_assessment(),
            "assessment_validated": False,
        },
        events=events,
    )

    session_factory = FakeSessionFactory(
        session=FakeSession(job, events),
        events=events,
    )

    with pytest.raises(
        InvalidInvestigationResultError,
        match="Incident assessment was not validated",
    ):
        await execute_and_persist_investigation(
            job_id=job.id,
            incident=incident,
            workflow=workflow,
            session_factory=session_factory,
        )

    assert session_factory.calls == 2
    assert job.status is JobStatus.FAILED
    assert job.error_message is not None
    assert "Incident assessment was not validated" in (
        job.error_message
    )
    assert events.index("session_exit") < events.index(
        "workflow"
    )


@pytest.mark.anyio
async def test_execution_requires_assessment() -> None:
    events: list[str] = []
    incident = load_incidents()["INC-DB-001"]
    job = make_pending_job()

    workflow = FakeWorkflow(
        result={
            "incident": incident,
            "assessment_validated": True,
        },
        events=events,
    )

    session_factory = FakeSessionFactory(
        session=FakeSession(job, events),
        events=events,
    )

    with pytest.raises(
        InvalidInvestigationResultError,
        match=(
            "Investigation did not produce an assessment"
        ),
    ):
        await execute_and_persist_investigation(
            job_id=job.id,
            incident=incident,
            workflow=workflow,
            session_factory=session_factory,
        )

    assert session_factory.calls == 2
    assert job.status is JobStatus.FAILED
    assert job.error_message is not None
    assert "did not produce an assessment" in (
        job.error_message
    )


@pytest.mark.anyio
async def test_execution_records_workflow_failure() -> None:
    events: list[str] = []
    incident = load_incidents()["INC-DB-001"]
    job = make_pending_job()

    class FailingWorkflow:
        async def ainvoke(
            self,
            input: dict[str, IncidentEvidence],
        ) -> InvestigationState:
            events.append("workflow")
            raise RuntimeError("Embedding provider unavailable")

    session = FakeSession(job, events)
    session_factory = FakeSessionFactory(
        session=session,
        events=events,
    )

    with pytest.raises(
        RuntimeError,
        match="Embedding provider unavailable",
    ):
        await execute_and_persist_investigation(
            job_id=job.id,
            incident=incident,
            workflow=FailingWorkflow(),
            session_factory=session_factory,
        )

    assert job.status is JobStatus.FAILED
    assert job.completed_at is not None
    assert job.error_message == (
        "RuntimeError: Embedding provider unavailable"
    )
    assert session.committed is True
    assert events.index("session_exit") < events.index(
        "workflow"
    )
    assert session_factory.calls == 2
