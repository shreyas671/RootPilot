import pytest

from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)
from apps.metadata_service.schemas.evaluation import (
    AssessmentEvaluationCase,
    RetrievalEvaluationCase,
)
from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.evaluation import (
    evaluate_assessment_case,
    evaluate_retrieval_case,
    run_pipeline_evaluation,
)
from apps.metadata_service.services.evaluation_loader import (
    load_evaluation_dataset,
)
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.runbook_loader import (
    load_runbooks,
)


class EvaluationRetriever:
    def __init__(self) -> None:
        self.sections = load_runbooks()

    async def retrieve(
        self,
        incident: IncidentEvidence,
        limit: int = 3,
    ) -> list[RetrievedRunbookSection]:
        runbook_id = (
            "RB-DB-001"
            if incident.incident_id == "INC-DB-001"
            else "RB-KAFKA-001"
        )
        section_order = {
            "diagnosis": 0,
            "likely-causes": 1,
            "remediation": 2,
            "signals": 3,
            "verification": 4,
        }
        matching_sections = sorted(
            (
                section
                for section in self.sections
                if section.runbook_id == runbook_id
            ),
            key=lambda section: section_order[
                section.citation_id.split("#", 1)[1]
            ],
        )

        return [
            RetrievedRunbookSection(
                section=section,
                score=0.95 - (index * 0.05),
            )
            for index, section in enumerate(
                matching_sections[:limit]
            )
        ]


class EvaluationAnalyst:
    async def analyze(
        self,
        incident: IncidentEvidence,
        retrieved_sections: list[
            RetrievedRunbookSection
        ],
    ) -> IncidentAssessment:
        citation_ids = [
            result.section.citation_id
            for result in retrieved_sections[:2]
        ]

        if incident.incident_id == "INC-DB-001":
            return IncidentAssessment(
                incident_id=incident.incident_id,
                root_cause=(
                    "The database connection pool is exhausted."
                ),
                supporting_evidence=[
                    "Active connections equal the pool maximum."
                ],
                recommended_actions=[
                    "Reduce leaked connection usage."
                ],
                verification_steps=[
                    "Verify pool waiters return to zero."
                ],
                confidence=0.9,
                citation_ids=citation_ids,
            )

        return IncidentAssessment(
            incident_id=incident.incident_id,
            root_cause=(
                "An incompatible event schema causes crashes."
            ),
            supporting_evidence=[
                "The required order_id field is missing."
            ],
            recommended_actions=[
                "Quarantine the incompatible event."
            ],
            verification_steps=[
                "Verify event processing resumes."
            ],
            confidence=0.9,
            citation_ids=citation_ids,
        )


class InvalidEvaluationAnalyst:
    async def analyze(
        self,
        incident: IncidentEvidence,
        retrieved_sections: list[
            RetrievedRunbookSection
        ],
    ) -> IncidentAssessment:
        return IncidentAssessment(
            incident_id="INC-KAFKA-001",
            root_cause="An unrelated schema failure.",
            supporting_evidence=["Unrelated evidence."],
            recommended_actions=["Inspect the event."],
            verification_steps=["Verify processing."],
            confidence=0.9,
            citation_ids=[
                retrieved_sections[0].section.citation_id,
            ],
        )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_retrieval_evaluation_calculates_metrics() -> None:
    incident = load_incidents()["INC-DB-001"]
    case = RetrievalEvaluationCase(
        case_id="RET-DB-001",
        incident_id=incident.incident_id,
        expected_citation_ids=[
            "RB-DB-001#diagnosis",
            "RB-DB-001#likely-causes",
        ],
        retrieval_limit=3,
        minimum_relevance_score=0.0,
    )

    result = await evaluate_retrieval_case(
        case=case,
        incident=incident,
        retriever=EvaluationRetriever(),
    )

    assert result.recall_at_k == 1.0
    assert result.reciprocal_rank == 1.0
    assert result.passed is True


def test_assessment_evaluation_detects_grounding_failure() -> None:
    incident = load_incidents()["INC-DB-001"]
    section = next(
        section
        for section in load_runbooks()
        if section.citation_id == "RB-DB-001#diagnosis"
    )
    case = AssessmentEvaluationCase(
        case_id="RCA-DB-001",
        incident_id=incident.incident_id,
        expected_citation_ids=[
            "RB-DB-001#diagnosis",
        ],
        retrieval_limit=3,
        minimum_relevance_score=0.0,
        required_root_cause_terms=["connection", "pool"],
        required_action_terms=["connection"],
        minimum_confidence=0.5,
    )
    assessment = IncidentAssessment(
        incident_id=incident.incident_id,
        root_cause="The connection pool is exhausted.",
        supporting_evidence=["The pool is full."],
        recommended_actions=["Reduce connection usage."],
        verification_steps=["Verify waiters clear."],
        confidence=0.9,
        citation_ids=["RB-KAFKA-001#diagnosis"],
    )

    result = evaluate_assessment_case(
        case=case,
        assessment=assessment,
        retrieved_sections=[
            RetrievedRunbookSection(
                section=section,
                score=0.9,
            )
        ],
    )

    assert result.incident_id_matches is True
    assert result.citations_grounded is False
    assert result.expected_citation_recall == 0.0
    assert result.passed is False


@pytest.mark.anyio
async def test_pipeline_evaluation_passes_fake_cases() -> None:
    summary = await run_pipeline_evaluation(
        dataset=load_evaluation_dataset(),
        incidents=load_incidents(),
        retriever=EvaluationRetriever(),
        analyst=EvaluationAnalyst(),
    )

    assert summary.retrieval.mean_recall_at_k == 1.0
    assert summary.retrieval.mean_reciprocal_rank == 1.0
    assert summary.retrieval.pass_rate == 1.0
    assert summary.assessment.pass_rate == 1.0
    assert (
        summary.assessment.mean_expected_citation_recall
        == 1.0
    )


@pytest.mark.anyio
async def test_pipeline_evaluation_records_graph_rejection() -> None:
    dataset = load_evaluation_dataset()
    dataset.assessment_cases = [
        dataset.assessment_cases[0]
    ]

    summary = await run_pipeline_evaluation(
        dataset=dataset,
        incidents=load_incidents(),
        retriever=EvaluationRetriever(),
        analyst=InvalidEvaluationAnalyst(),
    )

    result = summary.assessment.cases[0]

    assert result.passed is False
    assert result.incident_id_matches is False
    assert result.evaluation_error is not None
    assert "incident ID does not match" in (
        result.evaluation_error
    )
