from typing import Protocol

from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)
from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)


class IncidentAnalyst(Protocol):
    async def analyze(
        self,
        incident: IncidentEvidence,
        retrieved_sections: list[
            RetrievedRunbookSection
        ],
    ) -> IncidentAssessment:
        ...