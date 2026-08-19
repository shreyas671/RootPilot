from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.metadata_service.api.incidents import (
    router as incidents_router,
)
from apps.metadata_service.api.investigation_reports import (
    router as investigation_reports_router,
)
from apps.metadata_service.api.jobs import router as jobs_router
from apps.metadata_service.config import get_settings
from apps.metadata_service.database import get_db_session
from apps.metadata_service.observability import (
    configure_logging,
    metrics_response,
    observe_request,
)

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="RootPilot Metadata Service",
    version="1.0.0",
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url=(
        "/redoc" if settings.docs_enabled else None
    ),
    openapi_url=(
        "/openapi.json"
        if settings.docs_enabled
        else None
    ),
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
        ],
    )

app.middleware("http")(observe_request)

app.include_router(jobs_router)
app.include_router(investigation_reports_router)
app.include_router(incidents_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "metadata-service",
    }


@app.get(
    "/metrics",
    include_in_schema=False,
)
async def metrics() -> object:
    return metrics_response()


@app.get("/ready")
async def readiness_check(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except (OSError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc

    return {
        "status": "ready",
        "service": "metadata-service",
        "database": "connected",
    }
