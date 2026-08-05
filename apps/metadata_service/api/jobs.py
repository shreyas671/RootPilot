from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.metadata_service.database import get_db_session
from apps.metadata_service.models.job import Job
from apps.metadata_service.schemas.job import JobCreate, JobResponse


router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
)


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    request: JobCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JobResponse:
    job = Job(input_path=request.input_path)

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