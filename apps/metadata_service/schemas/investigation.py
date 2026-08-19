from typing import NotRequired, TypedDict

from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)


class InvestigationState(TypedDict):
    incident: IncidentEvidence
    retrieved_sections: NotRequired[
        list[RetrievedRunbookSection]
    ]