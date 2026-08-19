from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.metadata_service.database import get_db_session
from apps.metadata_service.schemas.investigation_report import (
    InvestigationReportResponse,
    InvestigationReportReview,
)
from apps.metadata_service.services.investigation_reports import (
    InvestigationReportAlreadyReviewedError,
    InvestigationReportNotFoundError,
    get_investigation_report,
    review_investigation_report,
)


router = APIRouter(
    prefix="/investigation-reports",
    tags=["investigation-reports"],
)


@router.get(
    "/{report_id}",
    response_model=InvestigationReportResponse,
)
async def get_report(
    report_id: UUID,
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> InvestigationReportResponse:
    try:
        report = await get_investigation_report(
            session,
            report_id,
        )
    except InvestigationReportNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation report not found",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Unable to retrieve investigation report",
        ) from exc

    return InvestigationReportResponse.model_validate(
        report
    )


@router.patch(
    "/{report_id}/review",
    response_model=InvestigationReportResponse,
)
async def review_report(
    report_id: UUID,
    request: InvestigationReportReview,
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> InvestigationReportResponse:
    try:
        report = await review_investigation_report(
            session,
            report_id,
            request,
        )
    except InvestigationReportNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation report not found",
        ) from exc
    except InvestigationReportAlreadyReviewedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Unable to review investigation report",
        ) from exc

    return InvestigationReportResponse.model_validate(
        report
    )