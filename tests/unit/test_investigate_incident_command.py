import argparse
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr

import apps.metadata_service.commands.investigate_incident as command_module
from apps.metadata_service.commands.investigate_incident import (
    format_investigation_result,
    format_persisted_investigation_result,
    parse_arguments,
    positive_integer,
    relevance_score,
)
from apps.metadata_service.models.investigation_report import (
    InvestigationReport,
    InvestigationReportStatus,
)
from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.runbook_loader import (
    load_runbooks,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_format_investigation_result() -> None:
    section = next(
        section
        for section in load_runbooks()
        if section.citation_id == "RB-DB-001#diagnosis"
    )

    retrieved_section = RetrievedRunbookSection(
        section=section,
        score=0.91,
    )

    assessment = IncidentAssessment(
        incident_id="INC-DB-001",
        root_cause=(
            "Database connections are not being released."
        ),
        supporting_evidence=[
            "The pool is at maximum capacity.",
        ],
        recommended_actions=[
            "Roll back the recent deployment.",
        ],
        verification_steps=[
            "Verify connection waiters return to zero.",
        ],
        confidence=0.91,
        citation_ids=[
            "RB-DB-001#diagnosis",
        ],
    )

    output = format_investigation_result(
        incident_id="INC-DB-001",
        embedding_model="embedding-test",
        analysis_model="analysis-test",
        retrieved_sections=[retrieved_section],
        assessment=assessment,
    )

    assert "Incident: INC-DB-001" in output
    assert "Embedding model: embedding-test" in output
    assert "Analysis model: analysis-test" in output
    assert "RB-DB-001#diagnosis score=0.9100" in output
    assert assessment.root_cause in output
    assert "Confidence: 0.91" in output
    assert "Roll back the recent deployment." in output
    assert "Verify connection waiters return to zero." in output


def test_positive_integer_validation() -> None:
    assert positive_integer("3") == 3

    with pytest.raises(
        argparse.ArgumentTypeError,
        match="value must be at least 1",
    ):
        positive_integer("0")


def test_relevance_score_validation() -> None:
    assert relevance_score("0.25") == 0.25

    with pytest.raises(
        argparse.ArgumentTypeError,
        match="value must be between -1.0 and 1.0",
    ):
        relevance_score("1.1")


def test_format_persisted_investigation_result() -> None:
    report_id = uuid4()
    job_id = uuid4()

    report = InvestigationReport(
        id=report_id,
        job_id=job_id,
        incident_id="INC-DB-001",
        root_cause="Database connection exhaustion",
        supporting_evidence=[
            "Connection usage reached its maximum.",
        ],
        recommended_actions=[
            "Reduce idle database connections.",
        ],
        verification_steps=[
            "Verify connection usage returns to normal.",
        ],
        confidence=0.92,
        citation_ids=[
            "RB-DB-001#diagnosis",
        ],
        status=(
            InvestigationReportStatus.PENDING_REVIEW
        ),
        reviewed_by=None,
        reviewer_feedback=None,
        reviewed_at=None,
    )

    output = format_persisted_investigation_result(
        report=report,
        embedding_model="embedding-test",
        analysis_model="analysis-test",
    )

    assert f"Report ID: {report_id}" in output
    assert f"Job ID: {job_id}" in output
    assert "Incident: INC-DB-001" in output
    assert "Review status: pending_review" in output
    assert "Database connection exhaustion" in output
    assert "Confidence: 0.92" in output
    assert "RB-DB-001#diagnosis" in output


def test_parse_arguments_accepts_job_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid4()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "investigate_incident",
            "INC-DB-001",
            "--job-id",
            str(job_id),
            "--limit",
            "5",
            "--minimum-score",
            "0.25",
        ],
    )

    arguments = parse_arguments()

    assert arguments.incident_id == "INC-DB-001"
    assert arguments.job_id == job_id
    assert arguments.limit == 5
    assert arguments.minimum_score == 0.25


@pytest.mark.anyio
async def test_persisted_command_executes_workflow(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    job_id = uuid4()
    report_id = uuid4()
    workflow = object()
    session_factory = object()
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class FakeRetriever:
        @classmethod
        async def create(
            cls,
            embedding_provider: object,
            sections: list[object],
        ) -> object:
            return object()

    client = FakeClient()

    def fake_build_graph(
        retriever: object,
        analyst: object,
        retrieval_limit: int,
        minimum_relevance_score: float,
    ) -> object:
        captured["retrieval_limit"] = retrieval_limit
        captured["minimum_score"] = (
            minimum_relevance_score
        )
        return workflow

    async def fake_execute(
        job_id: object,
        incident: object,
        workflow: object,
        session_factory: object,
    ) -> InvestigationReport:
        captured["job_id"] = job_id
        captured["incident"] = incident
        captured["workflow"] = workflow
        captured["session_factory"] = session_factory

        return InvestigationReport(
            id=report_id,
            job_id=job_id,
            incident_id="INC-DB-001",
            root_cause="Database connection exhaustion",
            supporting_evidence=["Pool is full."],
            recommended_actions=["Reduce connections."],
            verification_steps=["Check pool usage."],
            confidence=0.92,
            citation_ids=["RB-DB-001#diagnosis"],
            status=(
                InvestigationReportStatus.PENDING_REVIEW
            ),
            reviewed_by=None,
            reviewer_feedback=None,
            reviewed_at=None,
        )

    monkeypatch.setattr(
        command_module,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key=SecretStr("test-key"),
            openai_embedding_model="embedding-test",
            openai_analysis_model="analysis-test",
        ),
    )
    monkeypatch.setattr(
        command_module,
        "AsyncOpenAI",
        lambda api_key: client,
    )
    monkeypatch.setattr(
        command_module,
        "OpenAIEmbeddingProvider",
        lambda client, model: object(),
    )
    monkeypatch.setattr(
        command_module,
        "InMemoryRunbookRetriever",
        FakeRetriever,
    )
    monkeypatch.setattr(
        command_module,
        "load_runbooks",
        lambda: [],
    )
    monkeypatch.setattr(
        command_module,
        "OpenAIIncidentAnalyst",
        lambda client, model: object(),
    )
    monkeypatch.setattr(
        command_module,
        "build_investigation_graph",
        fake_build_graph,
    )
    monkeypatch.setattr(
        command_module,
        "get_session_factory",
        lambda: session_factory,
    )
    monkeypatch.setattr(
        command_module,
        "execute_and_persist_investigation",
        fake_execute,
    )

    await command_module.investigate_incident(
        incident_id="INC-DB-001",
        retrieval_limit=4,
        job_id=job_id,
        minimum_relevance_score=0.25,
    )

    assert captured["job_id"] == job_id
    assert captured["workflow"] is workflow
    assert captured["session_factory"] is session_factory
    assert captured["retrieval_limit"] == 4
    assert captured["minimum_score"] == 0.25
    assert client.closed is True

    output = capsys.readouterr().out

    assert f"Report ID: {report_id}" in output
    assert "Review status: pending_review" in output
