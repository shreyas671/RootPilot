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
    InvestigationReviewEventResponse,
)
from apps.metadata_service.services.investigation_reports import (
    InvestigationReportAlreadyReviewedError,
    InvestigationReportNotFoundError,
    get_investigation_report,
    list_investigation_review_events,
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


@router.get(
    "/{report_id}/review-events",
    response_model=list[InvestigationReviewEventResponse],
)
async def get_review_events(
    report_id: UUID,
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> list[InvestigationReviewEventResponse]:
    try:
        events = await list_investigation_review_events(
            session=session,
            report_id=report_id,
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
            detail="Unable to retrieve review events",
        ) from exc

    return [
        InvestigationReviewEventResponse.model_validate(
            event
        )
        for event in events
    ]


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
