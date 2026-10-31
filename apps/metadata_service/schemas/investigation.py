from typing import NotRequired, TypedDict

from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)
from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.react import (
    InvestigationStep,
    ReactDecision,
    ReactTerminationReason,
    ToolObservation,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)


class InvestigationState(TypedDict):
    incident: IncidentEvidence
    retrieved_sections: NotRequired[
        list[RetrievedRunbookSection]
    ]
    assessment: NotRequired[IncidentAssessment]
    assessment_validated: NotRequired[bool]
    current_decision: NotRequired[ReactDecision]
    observations: NotRequired[list[ToolObservation]]
    react_steps: NotRequired[list[InvestigationStep]]
    observed_evidence_ids: NotRequired[list[str]]
    executed_action_fingerprints: NotRequired[list[str]]
    iteration_count: NotRequired[int]
    tool_call_count: NotRequired[int]
    tool_error_count: NotRequired[int]
    no_progress_count: NotRequired[int]
    assessment_repair_count: NotRequired[int]
    validation_error: NotRequired[str | None]
    assessment_generation_failed: NotRequired[bool]
    react_started_at: NotRequired[float]
    termination_reason: NotRequired[
        ReactTerminationReason
    ]
