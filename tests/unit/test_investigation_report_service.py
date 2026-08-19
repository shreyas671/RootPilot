from datetime import UTC, datetime
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
from apps.metadata_service.schemas.investigation_report import (
    InvestigationReportCreate,
    InvestigationReportReview,
)
from apps.metadata_service.services.investigation_reports import (
    InvestigationReportAlreadyReviewedError,
    InvestigationReportNotFoundError,
    JobNotFoundError,
    JobNotPendingError,
    JobNotProcessingError,
    create_investigation_report,
    get_investigation_report,
    mark_investigation_job_failed,
    review_investigation_report,
    start_investigation_job,
)


class FakeSession:
    def __init__(self) -> None:
        self.job_to_return: Job | None = None
        self.report_to_return: (
            InvestigationReport | None
        ) = None
        self.added_report: (
            InvestigationReport | None
        ) = None
        self.get_calls: list[
            tuple[type[object], UUID, bool]
        ] = []
        self.committed = False
        self.rolled_back = False

    def add(
        self,
        report: InvestigationReport,
    ) -> None:
        self.added_report = report

    async def get(
        self,
        model: type[object],
        object_id: UUID,
        *,
        with_for_update: bool = False,
    ) -> object | None:
        self.get_calls.append(
            (
                model,
                object_id,
                with_for_update,
            )
        )

        if model is Job:
            if (
                self.job_to_return is not None
                and self.job_to_return.id == object_id
            ):
                return self.job_to_return

            return None

        if model is InvestigationReport:
            if (
                self.report_to_return is not None
                and self.report_to_return.id == object_id
            ):
                return self.report_to_return

            return None

        raise AssertionError("Unexpected model")

    async def flush(self) -> None:
        now = datetime.now(UTC)

        if self.added_report is not None:
            self.added_report.id = uuid4()
            self.added_report.created_at = now
            self.added_report.updated_at = now

        if self.report_to_return is not None:
            self.report_to_return.updated_at = now

        if self.job_to_return is not None:
            self.job_to_return.updated_at = now

    async def refresh(
        self,
        record: object,
    ) -> None:
        assert (
            record is self.added_report
            or record is self.report_to_return
        )

    async def commit(self) -> None:
        self.committed = True
        self.rolled_back = False

    async def rollback(self) -> None:
        self.committed = False
        self.rolled_back = True


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def make_job(status: JobStatus) -> Job:
    now = datetime.now(UTC)

    return Job(
        id=uuid4(),
        input_path="data/incidents/INC-DB-001.json",
        status=status,
        error_message=None,
        started_at=now,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )


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
            "RB-DB-001#connection-exhaustion",
        ],
    )


def make_report(
    status: InvestigationReportStatus,
) -> InvestigationReport:
    now = datetime.now(UTC)
    assessment = make_assessment()

    return InvestigationReport(
        id=uuid4(),
        job_id=uuid4(),
        incident_id=assessment.incident_id,
        root_cause=assessment.root_cause,
        supporting_evidence=(
            assessment.supporting_evidence
        ),
        recommended_actions=(
            assessment.recommended_actions
        ),
        verification_steps=(
            assessment.verification_steps
        ),
        confidence=assessment.confidence,
        citation_ids=assessment.citation_ids,
        status=status,
        reviewed_by=None,
        reviewer_feedback=None,
        reviewed_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.anyio
async def test_create_report_completes_job() -> None:
    session = FakeSession()
    job = make_job(JobStatus.PROCESSING)
    session.job_to_return = job

    request = InvestigationReportCreate(
        job_id=job.id,
        assessment=make_assessment(),
    )

    report = await create_investigation_report(
        session,
        request,
    )

    assert report is session.added_report
    assert report.incident_id == "INC-DB-001"
    assert report.status is (
        InvestigationReportStatus.PENDING_REVIEW
    )
    assert report.job_id == job.id

    assert job.status is JobStatus.COMPLETED
    assert job.completed_at is not None
    assert session.get_calls[0] == (
        Job,
        job.id,
        True,
    )
    assert session.committed is True
    assert session.rolled_back is False


@pytest.mark.anyio
async def test_create_report_rejects_missing_job() -> None:
    session = FakeSession()
    request = InvestigationReportCreate(
        job_id=uuid4(),
        assessment=make_assessment(),
    )

    with pytest.raises(JobNotFoundError):
        await create_investigation_report(
            session,
            request,
        )

    assert session.added_report is None
    assert session.rolled_back is True


@pytest.mark.anyio
async def test_create_report_requires_processing_job() -> None:
    session = FakeSession()
    job = make_job(JobStatus.PENDING)
    session.job_to_return = job

    request = InvestigationReportCreate(
        job_id=job.id,
        assessment=make_assessment(),
    )

    with pytest.raises(JobNotProcessingError):
        await create_investigation_report(
            session,
            request,
        )

    assert job.status is JobStatus.PENDING
    assert session.added_report is None
    assert session.rolled_back is True


@pytest.mark.anyio
async def test_start_investigation_job() -> None:
    session = FakeSession()
    job = make_job(JobStatus.PENDING)
    job.started_at = None
    session.job_to_return = job

    result = await start_investigation_job(
        session=session,
        job_id=job.id,
    )

    assert result is job
    assert job.status is JobStatus.PROCESSING
    assert job.started_at is not None
    assert job.completed_at is None
    assert job.error_message is None
    assert session.get_calls[0] == (
        Job,
        job.id,
        True,
    )
    assert session.committed is True


@pytest.mark.anyio
async def test_start_requires_pending_job() -> None:
    session = FakeSession()
    job = make_job(JobStatus.COMPLETED)
    session.job_to_return = job

    with pytest.raises(JobNotPendingError):
        await start_investigation_job(
            session=session,
            job_id=job.id,
        )

    assert job.status is JobStatus.COMPLETED
    assert session.rolled_back is True


@pytest.mark.anyio
async def test_mark_investigation_job_failed() -> None:
    session = FakeSession()
    job = make_job(JobStatus.PROCESSING)
    session.job_to_return = job

    result = await mark_investigation_job_failed(
        session=session,
        job_id=job.id,
        error_message="  Retrieval failed  ",
    )

    assert result is job
    assert job.status is JobStatus.FAILED
    assert job.completed_at is not None
    assert job.error_message == "Retrieval failed"
    assert session.get_calls[0] == (
        Job,
        job.id,
        True,
    )
    assert session.committed is True


@pytest.mark.anyio
async def test_get_existing_report() -> None:
    session = FakeSession()
    report = make_report(
        InvestigationReportStatus.PENDING_REVIEW
    )
    session.report_to_return = report

    result = await get_investigation_report(
        session,
        report.id,
    )

    assert result is report
    assert session.get_calls[0] == (
        InvestigationReport,
        report.id,
        False,
    )


@pytest.mark.anyio
async def test_review_pending_report() -> None:
    session = FakeSession()
    report = make_report(
        InvestigationReportStatus.PENDING_REVIEW
    )
    session.report_to_return = report

    request = InvestigationReportReview(
        status=InvestigationReportStatus.APPROVED,
        reviewed_by="operator@example.com",
    )

    result = await review_investigation_report(
        session,
        report.id,
        request,
    )

    assert result is report
    assert report.status is (
        InvestigationReportStatus.APPROVED
    )
    assert report.reviewed_by == "operator@example.com"
    assert report.reviewed_at is not None
    assert session.get_calls[0] == (
        InvestigationReport,
        report.id,
        True,
    )
    assert session.committed is True


@pytest.mark.anyio
async def test_report_cannot_be_reviewed_twice() -> None:
    session = FakeSession()
    report = make_report(
        InvestigationReportStatus.APPROVED
    )
    session.report_to_return = report

    request = InvestigationReportReview(
        status=InvestigationReportStatus.REJECTED,
        reviewed_by="second-operator@example.com",
        reviewer_feedback="Incorrect diagnosis.",
    )

    with pytest.raises(
        InvestigationReportAlreadyReviewedError
    ):
        await review_investigation_report(
            session,
            report.id,
            request,
        )

    assert report.status is (
        InvestigationReportStatus.APPROVED
    )
    assert session.rolled_back is True


@pytest.mark.anyio
async def test_review_rejects_missing_report() -> None:
    session = FakeSession()
    report_id = uuid4()

    request = InvestigationReportReview(
        status=InvestigationReportStatus.APPROVED,
        reviewed_by="operator@example.com",
    )

    with pytest.raises(
        InvestigationReportNotFoundError
    ):
        await review_investigation_report(
            session,
            report_id,
            request,
        )

    assert session.rolled_back is True
