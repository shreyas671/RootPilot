from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
TimeRange = Literal["15m", "30m", "1h", "2h", "6h", "24h"]


class ReactModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryMetricsAction(ReactModel):
    tool: Literal["query_metrics"]
    service: NonEmptyText
    metric: NonEmptyText
    time_range: TimeRange


class SearchLogsAction(ReactModel):
    tool: Literal["search_logs"]
    service: NonEmptyText
    pattern: NonEmptyText
    time_range: TimeRange


class GetRecentDeploymentsAction(ReactModel):
    tool: Literal["get_recent_deployments"]
    service: NonEmptyText
    time_range: TimeRange


class CheckServiceHealthAction(ReactModel):
    tool: Literal["check_service_health"]
    service: NonEmptyText


class SearchRunbooksAction(ReactModel):
    tool: Literal["search_runbooks"]
    query: NonEmptyText
    limit: int = Field(ge=1, le=10)


class RequestAdditionalEvidenceAction(ReactModel):
    tool: Literal["request_additional_evidence"]
    evidence_needed: list[NonEmptyText] = Field(min_length=1)
    reason: NonEmptyText


class FinalizeAssessmentAction(ReactModel):
    tool: Literal["finalize_assessment"]
    evidence_ids: list[NonEmptyText] = Field(min_length=1)


ReactAction = Annotated[
    QueryMetricsAction
    | SearchLogsAction
    | GetRecentDeploymentsAction
    | CheckServiceHealthAction
    | SearchRunbooksAction
    | RequestAdditionalEvidenceAction
    | FinalizeAssessmentAction,
    Field(discriminator="tool"),
]


class ReactDecision(ReactModel):
    hypothesis: NonEmptyText
    rationale: NonEmptyText
    action: ReactAction


class ToolObservation(ReactModel):
    tool: NonEmptyText
    summary: NonEmptyText
    evidence_ids: list[str] = Field(default_factory=list)
    result_count: int = Field(default=0, ge=0)
    is_error: bool = False


class InvestigationStep(ReactModel):
    iteration: int = Field(ge=1)
    tool: NonEmptyText
    hypothesis: NonEmptyText
    rationale: NonEmptyText
    arguments: dict[str, object]
    observation: NonEmptyText
    evidence_ids: list[str] = Field(default_factory=list)
    new_evidence_count: int = Field(default=0, ge=0)
    is_error: bool = False


ReactTerminationReason = Literal[
    "model_finished",
    "max_iterations",
    "max_tool_calls",
    "no_progress",
    "runtime_limit",
    "tool_error_limit",
]
