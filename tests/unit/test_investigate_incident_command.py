import argparse

import pytest

from apps.metadata_service.commands.investigate_incident import (
    format_investigation_result,
    positive_integer,
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