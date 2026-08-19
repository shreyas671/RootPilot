from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.metadata_service.models.investigation_report import (
    InvestigationReport,
    InvestigationReportStatus,
)
from apps.metadata_service.models.job import Job, JobStatus
from apps.metadata_service.schemas.investigation_report import (
    InvestigationReportCreate,
    InvestigationReportReview,
)


class JobNotFoundError(LookupError):
    pass


class JobNotProcessingError(ValueError):
    pass


class InvestigationReportNotFoundError(LookupError):
    pass


class InvestigationReportAlreadyReviewedError(
    ValueError
):
    pass


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

    report.status = request.status
    report.reviewed_by = request.reviewed_by
    report.reviewer_feedback = (
        request.reviewer_feedback
    )
    report.reviewed_at = datetime.now(UTC)

    try:
        await session.flush()
        await session.refresh(report)
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    return report