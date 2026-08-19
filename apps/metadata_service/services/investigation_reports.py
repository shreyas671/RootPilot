from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.metadata_service.models.investigation_report import (
    InvestigationReport,
    InvestigationReportStatus,
)
from apps.metadata_service.models.job import Job, JobStatus
from apps.metadata_service.models.investigation_review_event import (
    InvestigationReviewEvent,
)
from apps.metadata_service.schemas.investigation_report import (
    InvestigationReportCreate,
    InvestigationReportReview,
)


class JobNotFoundError(LookupError):
    pass


class JobNotProcessingError(ValueError):
    pass


class JobNotPendingError(ValueError):
    pass


class InvestigationReportNotFoundError(LookupError):
    pass


class InvestigationReportAlreadyReviewedError(
    ValueError
):
    pass


async def start_investigation_job(
    session: AsyncSession,
    job_id: UUID,
) -> Job:
    try:
        job = await session.get(
            Job,
            job_id,
            with_for_update=True,
        )
    except SQLAlchemyError:
        await session.rollback()
        raise

    if job is None:
        await session.rollback()

        raise JobNotFoundError(
            f"Job {job_id} not found"
        )

    if job.status is not JobStatus.PENDING:
        await session.rollback()

        raise JobNotPendingError(
            f"Job {job_id} must be pending "
            "before investigation starts"
        )

    job.status = JobStatus.PROCESSING
    job.started_at = datetime.now(UTC)
    job.completed_at = None
    job.error_message = None

    try:
        await session.flush()
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    return job


async def mark_investigation_job_failed(
    session: AsyncSession,
    job_id: UUID,
    error_message: str,
) -> Job:
    try:
        job = await session.get(
            Job,
            job_id,
            with_for_update=True,
        )
    except SQLAlchemyError:
        await session.rollback()
        raise

    if job is None:
        await session.rollback()

        raise JobNotFoundError(
            f"Job {job_id} not found"
        )

    if job.status is not JobStatus.PROCESSING:
        await session.rollback()

        raise JobNotProcessingError(
            f"Job {job_id} must be processing "
            "before it can be marked failed"
        )

    normalized_error = error_message.strip()

    if not normalized_error:
        normalized_error = "Investigation execution failed"

    job.status = JobStatus.FAILED
    job.completed_at = datetime.now(UTC)
    job.error_message = normalized_error[:4000]

    try:
        await session.flush()
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    return job


async def create_investigation_report(
    session: AsyncSession,
    request: InvestigationReportCreate,
) -> InvestigationReport:
    try:
        job = await session.get(
            Job,
            request.job_id,
            with_for_update=True,
        )
    except SQLAlchemyError:
        await session.rollback()
        raise

    if job is None:
        await session.rollback()

        raise JobNotFoundError(
            f"Job {request.job_id} not found"
        )

    if job.status is not JobStatus.PROCESSING:
        await session.rollback()

        raise JobNotProcessingError(
            f"Job {request.job_id} must be processing "
            "before a report can be created"
        )

    assessment = request.assessment
    now = datetime.now(UTC)

    report = InvestigationReport(
        job_id=request.job_id,
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
        status=(
            InvestigationReportStatus.PENDING_REVIEW
        ),
        reviewed_by=None,
        reviewer_feedback=None,
        reviewed_at=None,
    )

    job.status = JobStatus.COMPLETED
    job.completed_at = now
    job.error_message = None

    try:
        session.add(report)
        await session.flush()
        await session.refresh(report)
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    return report


async def get_investigation_report(
    session: AsyncSession,
    report_id: UUID,
) -> InvestigationReport:
    try:
        report = await session.get(
            InvestigationReport,
            report_id,
        )
    except SQLAlchemyError:
        await session.rollback()
        raise

    if report is None:
        await session.rollback()

        raise InvestigationReportNotFoundError(
            f"Investigation report {report_id} not found"
        )

    return report


async def list_investigation_review_events(
    session: AsyncSession,
    report_id: UUID,
) -> list[InvestigationReviewEvent]:
    try:
        report = await session.get(
            InvestigationReport,
            report_id,
        )
    except SQLAlchemyError:
        await session.rollback()
        raise

    if report is None:
        await session.rollback()

        raise InvestigationReportNotFoundError(
            f"Investigation report {report_id} not found"
        )

    statement = (
        select(InvestigationReviewEvent)
        .where(
            InvestigationReviewEvent.report_id
            == report_id
        )
        .order_by(
            InvestigationReviewEvent.created_at,
            InvestigationReviewEvent.id,
        )
    )

    try:
        result = await session.execute(statement)
    except SQLAlchemyError:
        await session.rollback()
        raise

    return list(result.scalars().all())


async def review_investigation_report(
    session: AsyncSession,
    report_id: UUID,
    request: InvestigationReportReview,
) -> InvestigationReport:
    try:
        report = await session.get(
            InvestigationReport,
            report_id,
            with_for_update=True,
        )
    except SQLAlchemyError:
        await session.rollback()
        raise

    if report is None:
        await session.rollback()

        raise InvestigationReportNotFoundError(
            f"Investigation report {report_id} not found"
        )

    if (
        report.status
        is not InvestigationReportStatus.PENDING_REVIEW
    ):
        await session.rollback()

        raise InvestigationReportAlreadyReviewedError(
            f"Investigation report {report_id} has "
            f"already been {report.status.value}"
        )

    previous_status = report.status
    report.status = request.status
    report.reviewed_by = request.reviewed_by
    report.reviewer_feedback = (
        request.reviewer_feedback
    )
    report.reviewed_at = datetime.now(UTC)
    review_event = InvestigationReviewEvent(
        report_id=report.id,
        previous_status=previous_status,
        new_status=request.status,
        reviewed_by=request.reviewed_by,
        reviewer_feedback=request.reviewer_feedback,
    )

    try:
        session.add(review_event)
        await session.flush()
        await session.refresh(report)
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    return report
