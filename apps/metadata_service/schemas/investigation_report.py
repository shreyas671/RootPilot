from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
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


class RetrievedSectionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: CitationId
    score: float = Field(ge=-1.0, le=1.0)
    content_hash: str = Field(
        pattern=r"^[a-f0-9]{64}$",
    )
    source_file: NonEmptyText


class InvestigationProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_model: NonEmptyText = "unknown"
    analysis_model: NonEmptyText = "unknown"
    prompt_version: NonEmptyText = "unknown"
    retrieval_backend: NonEmptyText = "memory"
    retrieval_limit: int = Field(default=3, ge=1)
    minimum_relevance_score: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
    )
    retrieved_sections: list[
        RetrievedSectionTrace
    ] = Field(default_factory=list)


class InvestigationReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    assessment: IncidentAssessment
    provenance: InvestigationProvenance = Field(
        default_factory=InvestigationProvenance,
    )


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
    embedding_model: str
    analysis_model: str
    prompt_version: str
    retrieval_backend: str
    retrieval_limit: int
    minimum_relevance_score: float
    retrieved_sections: list[RetrievedSectionTrace]
    status: InvestigationReportStatus
    reviewed_by: str | None
    reviewer_feedback: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InvestigationReviewEventResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: UUID
    report_id: UUID
    previous_status: InvestigationReportStatus
    new_status: InvestigationReportStatus
    reviewed_by: str
    reviewer_feedback: str | None
    created_at: datetime
