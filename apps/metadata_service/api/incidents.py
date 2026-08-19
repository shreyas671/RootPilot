from typing import Annotated

from fastapi import APIRouter, Depends

from apps.metadata_service.schemas.incident import (
    IncidentCatalogEntry,
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
    prefix="/incidents",
    tags=["incidents"],
)


@router.get("", response_model=list[IncidentCatalogEntry])
async def list_incidents(
    principal: Annotated[
        Principal,
        Depends(require_roles(Role.VIEWER)),
    ],
) -> list[IncidentCatalogEntry]:
    return load_incident_catalog()
