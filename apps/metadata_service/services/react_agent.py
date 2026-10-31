from typing import Protocol

from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)
from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.react import (
    InvestigationStep,
    ReactDecision,
    ToolObservation,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)


class ReActPlanner(Protocol):
    async def decide(
        self,
        incident: IncidentEvidence,
        steps: list[InvestigationStep],
        observations: list[ToolObservation],
        remaining_iterations: int,
        remaining_tool_calls: int,
    ) -> ReactDecision:
        ...


class ReActAssessmentAnalyst(Protocol):
    async def analyze_react(
        self,
        incident: IncidentEvidence,
        observations: list[ToolObservation],
        retrieved_sections: list[
            RetrievedRunbookSection
        ],
        validation_feedback: str | None = None,
    ) -> IncidentAssessment:
        ...
