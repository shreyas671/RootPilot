from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.metadata_service.models.job import Job, JobStatus
from apps.metadata_service.services.investigation_reports import (
    JobNotFoundError,
    JobNotProcessingError,
)


async def claim_next_investigation_job(
    session: AsyncSession,
    worker_id: str,
    lease_seconds: int,
    target_job_id: UUID | None = None,
) -> Job | None:
    if not worker_id.strip():
        raise ValueError("Worker ID cannot be empty")

    if lease_seconds < 1:
        raise ValueError(
            "Lease duration must be at least one second"
        )

    now = datetime.now(UTC)
    exhausted_statement = update(Job).where(
        Job.status == JobStatus.PROCESSING,
        Job.lease_expires_at.is_not(None),
        Job.lease_expires_at < now,
        Job.attempt_count >= Job.max_attempts,
    )

    if target_job_id is not None:
        exhausted_statement = exhausted_statement.where(
            Job.id == target_job_id
        )

    try:
        await session.execute(
            exhausted_statement.values(
                status=JobStatus.FAILED,
                completed_at=now,
                claimed_by=None,
                lease_expires_at=None,
                error_message=(
                    "Worker lease expired after maximum "
                    "attempts"
                ),
            )
        )
    except SQLAlchemyError:
        await session.rollback()
        raise
    available = or_(
        and_(
            Job.status == JobStatus.PENDING,
            Job.scheduled_at <= now,
        ),
        and_(
            Job.status == JobStatus.PROCESSING,
            Job.lease_expires_at.is_not(None),
            Job.lease_expires_at < now,
        ),
    )
    statement = select(Job).where(
        available,
        Job.attempt_count < Job.max_attempts,
    )

    if target_job_id is not None:
        statement = statement.where(
            Job.id == target_job_id
        )

    statement = (
        statement
        .order_by(Job.scheduled_at, Job.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )

    try:
        result = await session.execute(statement)
        job = result.scalar_one_or_none()
    except SQLAlchemyError:
        await session.rollback()
        raise

    if job is None:
        await session.commit()
        return None

    job.status = JobStatus.PROCESSING
    job.attempt_count += 1
    job.claimed_by = worker_id.strip()[:255]
    job.lease_expires_at = now + timedelta(
        seconds=lease_seconds
    )
    job.started_at = job.started_at or now
    job.completed_at = None
    job.error_message = None

    try:
        await session.flush()
        await session.refresh(job)
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    return job


async def requeue_investigation_job(
    session: AsyncSession,
    job_id: UUID,
    error_message: str,
    retry_delay_seconds: float,
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
        raise JobNotFoundError(f"Job {job_id} not found")

    if job.status is not JobStatus.PROCESSING:
        await session.rollback()
        raise JobNotProcessingError(
            f"Job {job_id} must be processing "
            "before it can be requeued"
        )

    normalized_error = error_message.strip()
    now = datetime.now(UTC)
    job.claimed_by = None
    job.lease_expires_at = None
    job.error_message = normalized_error[:4000]

    if job.attempt_count >= job.max_attempts:
        job.status = JobStatus.FAILED
        job.completed_at = now
    else:
        job.status = JobStatus.PENDING
        job.completed_at = None
        job.scheduled_at = now + timedelta(
            seconds=max(0.0, retry_delay_seconds)
        )

    try:
        await session.flush()
        await session.refresh(job)
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    return job


async def renew_investigation_job_lease(
    session: AsyncSession,
    job_id: UUID,
    worker_id: str,
    lease_seconds: int,
) -> Job:
    normalized_worker_id = worker_id.strip()

    if not normalized_worker_id:
        raise ValueError("Worker ID cannot be empty")

    if lease_seconds < 1:
        raise ValueError(
            "Lease duration must be at least one second"
        )

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
        raise JobNotFoundError(f"Job {job_id} not found")

    if (
        job.status is not JobStatus.PROCESSING
        or job.claimed_by != normalized_worker_id
    ):
        await session.rollback()
        raise JobNotProcessingError(
            f"Job {job_id} is not leased by worker "
            f"{normalized_worker_id}"
        )

    job.lease_expires_at = datetime.now(UTC) + timedelta(
        seconds=lease_seconds
    )

    try:
        await session.flush()
        await session.refresh(job)
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    return job
