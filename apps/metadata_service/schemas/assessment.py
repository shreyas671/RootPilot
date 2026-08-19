from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

NonEmptyText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
    ),
]

CitationId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=(
            r"^RB-[A-Z]+-\d{3}#[a-z0-9-]+$"
        ),
    ),
]


class IncidentAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(
        pattern=r"^INC-[A-Z]+-\d{3}$",
    )
    root_cause: NonEmptyText
    supporting_evidence: list[NonEmptyText] = Field(
        min_length=1,
    )
    recommended_actions: list[NonEmptyText] = Field(
        min_length=1,
    )
    verification_steps: list[NonEmptyText] = Field(
        min_length=1,
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    citation_ids: list[CitationId] = Field(
        min_length=1,
    )

    @field_validator("citation_ids")
    @classmethod
    def validate_unique_citations(
        cls,
        citation_ids: list[str],
    ) -> list[str]:
        if len(citation_ids) != len(set(citation_ids)):
            raise ValueError(
                "citation IDs must be unique"
            )

        return citation_ids