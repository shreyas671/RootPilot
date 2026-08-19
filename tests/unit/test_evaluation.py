import argparse

import pytest

from apps.metadata_service.commands.evaluate_pipeline import (
    unit_interval,
)
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
        runbook_id = {
            "INC-CACHE-001": "RB-CACHE-001",
            "INC-DB-001": "RB-DB-001",
            "INC-KAFKA-001": "RB-KAFKA-001",
            "INC-MEMORY-001": "RB-MEMORY-001",
            "INC-TLS-001": "RB-TLS-001",
        }[incident.incident_id]
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

        assessment_text = {
            "INC-CACHE-001": (
                "A cache hot key exhausted Redis connections.",
                "Fix the cache access pattern.",
            ),
            "INC-DB-001": (
                "The database connection pool is exhausted.",
                "Reduce leaked connection usage.",
            ),
            "INC-KAFKA-001": (
                "An incompatible event schema causes crashes.",
                "Quarantine the incompatible event.",
            ),
            "INC-MEMORY-001": (
                "A native decoder memory leak causes OOM restarts.",
                "Fix memory lifecycle and roll back the decoder.",
            ),
            "INC-TLS-001": (
                "The TLS certificate expired.",
                "Deploy a renewed certificate.",
            ),
        }
        root_cause, action = assessment_text[
            incident.incident_id
        ]

        return IncidentAssessment(
            incident_id=incident.incident_id,
            root_cause=root_cause,
            supporting_evidence=[
                "Incident evidence matches the runbook signals."
            ],
            recommended_actions=[action],
            verification_steps=[
                "Verify service health returns to normal."
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


def test_evaluation_threshold_validation() -> None:
    assert unit_interval("0.95") == 0.95

    with pytest.raises(argparse.ArgumentTypeError):
        unit_interval("1.1")


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
