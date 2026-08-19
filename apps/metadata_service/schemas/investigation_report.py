from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    model_validator,
)

from apps.metadata_service.models.investigation_report import (
    InvestigationReportStatus,
)
from apps.metadata_service.schemas.assessment import (
    CitationId,
    IncidentAssessment,
    NonEmptyText,
)


ReviewerName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=255,
    ),
]

ReviewerFeedback = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=4000,
    ),
]


class InvestigationReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    assessment: IncidentAssessment


class InvestigationReportReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: InvestigationReportStatus
    reviewed_by: ReviewerName
    reviewer_feedback: ReviewerFeedback | None = None

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        if (
            self.status
            is InvestigationReportStatus.PENDING_REVIEW
        ):
            raise ValueError(
                "review status must be approved or rejected"
            )

        if (
            self.status
            is InvestigationReportStatus.REJECTED
            and self.reviewer_feedback is None
        ):
            raise ValueError(
                "reviewer_feedback is required when "
                "rejecting a report"
            )

        return self


class InvestigationReportResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: UUID
    job_id: UUID
    incident_id: str
    root_cause: NonEmptyText
    supporting_evidence: list[NonEmptyText]
    recommended_actions: list[NonEmptyText]
    verification_steps: list[NonEmptyText]
    confidence: float
    citation_ids: list[CitationId]
    status: InvestigationReportStatus
    reviewed_by: str | None
    reviewer_feedback: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime