import json
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
        json_schema_extra={"uniqueItems": True},
    )

    @classmethod
    def model_validate_model_json(
        cls,
        json_data: str,
    ) -> "IncidentAssessment":
        """Validate model JSON after safe citation normalization."""
        data = json.loads(json_data)
        if isinstance(data, dict):
            citation_ids = data.get("citation_ids")
            if isinstance(citation_ids, list):
                data["citation_ids"] = list(
                    dict.fromkeys(citation_ids)
                )
        return cls.model_validate(data)

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
