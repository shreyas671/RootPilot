from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from apps.metadata_service.schemas.assessment import (
    CitationId,
)

EvaluationCaseId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^[A-Z]+-[A-Z]+-\d{3}$",
    ),
]

IncidentId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^INC-[A-Z]+-\d{3}$",
    ),
]

EvaluationTerm = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
    ),
]


class RetrievalEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: EvaluationCaseId
    incident_id: IncidentId
    expected_citation_ids: list[CitationId] = Field(
        min_length=1,
    )
    retrieval_limit: int = Field(ge=1)
    minimum_relevance_score: float = Field(
        ge=-1.0,
        le=1.0,
    )

    @field_validator("expected_citation_ids")
    @classmethod
    def validate_unique_citations(
        cls,
        citation_ids: list[str],
    ) -> list[str]:
        if len(citation_ids) != len(set(citation_ids)):
            raise ValueError(
                "expected citation IDs must be unique"
            )

        return citation_ids


class AssessmentEvaluationCase(
    RetrievalEvaluationCase
):
    required_root_cause_terms: list[
        EvaluationTerm
    ] = Field(min_length=1)
    required_action_terms: list[
        EvaluationTerm
    ] = Field(min_length=1)
    minimum_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )


class EvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retrieval_cases: list[
        RetrievalEvaluationCase
    ] = Field(min_length=1)
    assessment_cases: list[
        AssessmentEvaluationCase
    ] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_case_ids(self) -> Self:
        case_ids = [
            case.case_id
            for case in (
                *self.retrieval_cases,
                *self.assessment_cases,
            )
        ]

        if len(case_ids) != len(set(case_ids)):
            raise ValueError(
                "evaluation case IDs must be unique"
            )

        return self


class RetrievalEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: EvaluationCaseId
    incident_id: IncidentId
    expected_citation_ids: list[CitationId]
    retrieved_citation_ids: list[CitationId]
    recall_at_k: float = Field(ge=0.0, le=1.0)
    reciprocal_rank: float = Field(ge=0.0, le=1.0)
    passed: bool


class RetrievalEvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cases: list[RetrievalEvaluationResult] = Field(
        min_length=1,
    )
    mean_recall_at_k: float = Field(ge=0.0, le=1.0)
    mean_reciprocal_rank: float = Field(
        ge=0.0,
        le=1.0,
    )
    pass_rate: float = Field(ge=0.0, le=1.0)


class AssessmentEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: EvaluationCaseId
    incident_id: IncidentId
    incident_id_matches: bool
    citations_grounded: bool
    expected_citation_recall: float = Field(
        ge=0.0,
        le=1.0,
    )
    root_cause_term_coverage: float = Field(
        ge=0.0,
        le=1.0,
    )
    action_term_coverage: float = Field(
        ge=0.0,
        le=1.0,
    )
    confidence_acceptable: bool
    evaluation_error: str | None = None
    passed: bool


class AssessmentEvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cases: list[AssessmentEvaluationResult] = Field(
        min_length=1,
    )
    mean_expected_citation_recall: float = Field(
        ge=0.0,
        le=1.0,
    )
    mean_root_cause_term_coverage: float = Field(
        ge=0.0,
        le=1.0,
    )
    mean_action_term_coverage: float = Field(
        ge=0.0,
        le=1.0,
    )
    pass_rate: float = Field(ge=0.0, le=1.0)


class PipelineEvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retrieval: RetrievalEvaluationSummary
    assessment: AssessmentEvaluationSummary
