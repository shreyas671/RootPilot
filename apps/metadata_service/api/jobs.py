from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.metadata_service.database import get_db_session
from apps.metadata_service.models.job import Job, JobStatus
from apps.metadata_service.schemas.job import (
    JobCreate,
    JobResponse,
    JobStatusUpdate,
)
from apps.metadata_service.security import (
    Principal,
    Role,
    require_roles,
)
from apps.metadata_service.services.incident_loader import (
    load_incident_catalog,
)

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
)


ALLOWED_STATUS_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING: {
        JobStatus.PROCESSING,
    },
    JobStatus.PROCESSING: {
        JobStatus.COMPLETED,
        JobStatus.FAILED,
    },
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: set(),
}


@router.get(
    "",
    response_model=list[JobResponse],
)
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[
        Principal,
        Depends(require_roles(Role.VIEWER)),
    ],
    job_status: Annotated[
        JobStatus | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[JobResponse]:
    statement = select(Job)

    if job_status is not None:
        statement = statement.where(
            Job.status == job_status
        )

    statement = statement.order_by(
        Job.created_at.desc(),
        Job.id,
    ).limit(limit).offset(offset)

    try:
        result = await session.execute(statement)
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Unable to list jobs",
        ) from exc

    return [
        JobResponse.model_validate(job)
        for job in result.scalars().all()
    ]


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    request: JobCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[
        Principal,
        Depends(require_roles(Role.OPERATOR)),
    ],
) -> JobResponse:
    catalog = {
        item.incident_id: item
        for item in load_incident_catalog()
    }
    incident = catalog.get(request.incident_id)

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unknown incident ID",
        )

    job = Job(
        input_path=incident.input_path,
        incident_id=request.incident_id,
        max_attempts=request.max_attempts,
    )

    try:
        session.add(job)
        await session.flush()
        await session.refresh(job)

        response = JobResponse.model_validate(job)

        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create job",
        ) from exc

    return response


@router.get(
    "/{job_id}",
    response_model=JobResponse,
)
async def get_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[
        Principal,
        Depends(require_roles(Role.VIEWER)),
    ],
) -> JobResponse:
    try:
        job = await session.get(Job, job_id)
    except SQLAlchemyError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve job",
        ) from exc

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return JobResponse.model_validate(job)


@router.patch(
    "/{job_id}/status",
    response_model=JobResponse,
)
async def update_job_status(
    job_id: UUID,
    request: JobStatusUpdate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[
        Principal,
        Depends(require_roles(Role.OPERATOR)),
    ],
) -> JobResponse:
    try:
        job = await session.get(
            Job,
            job_id,
            with_for_update=True,
        )
    except SQLAlchemyError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve job",
        ) from exc

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    current_status = job.status
    allowed_statuses = ALLOWED_STATUS_TRANSITIONS[current_status]

    if request.status not in allowed_statuses:
        error_detail = (
            f"Cannot transition job from "
            f"{current_status.value} to {request.status.value}"
        )

        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail,
        )

    now = datetime.now(UTC)

    job.status = request.status

    if request.status is JobStatus.PROCESSING:
        job.started_at = now
        job.completed_at = None
        job.error_message = None

    elif request.status is JobStatus.COMPLETED:
        job.completed_at = now
        job.error_message = None
        job.claimed_by = None
        job.lease_expires_at = None

    elif request.status is JobStatus.FAILED:
        job.completed_at = now
        job.error_message = request.error_message
        job.claimed_by = None
        job.lease_expires_at = None

    try:
        await session.flush()
        await session.refresh(job)

        response = JobResponse.model_validate(job)

        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update job status",
        ) from exc

    return response
