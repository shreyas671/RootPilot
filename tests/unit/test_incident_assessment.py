import pytest
from pydantic import ValidationError

from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)


def make_assessment_data() -> dict[str, object]:
    return {
        "incident_id": "INC-DB-001",
        "root_cause": (
            "Database connections are not being released."
        ),
        "supporting_evidence": [
            "Active connections equal the pool maximum.",
        ],
        "recommended_actions": [
            "Roll back the recent deployment.",
        ],
        "verification_steps": [
            "Verify that connection waiters return to zero.",
        ],
        "confidence": 0.91,
        "citation_ids": [
            "RB-DB-001#diagnosis",
        ],
    }


def test_incident_assessment_accepts_valid_data() -> None:
    assessment = IncidentAssessment(
        **make_assessment_data()
    )

    assert assessment.incident_id == "INC-DB-001"
    assert assessment.confidence == 0.91
    assert assessment.citation_ids == [
        "RB-DB-001#diagnosis",
    ]


def test_incident_assessment_rejects_blank_root_cause() -> None:
    data = make_assessment_data()
    data["root_cause"] = "   "

    with pytest.raises(ValidationError):
        IncidentAssessment(**data)


@pytest.mark.parametrize(
    "confidence",
    [
        -0.1,
        1.1,
    ],
)
def test_incident_assessment_rejects_invalid_confidence(
    confidence: float,
) -> None:
    data = make_assessment_data()
    data["confidence"] = confidence

    with pytest.raises(ValidationError):
        IncidentAssessment(**data)


def test_incident_assessment_rejects_invalid_citation() -> None:
    data = make_assessment_data()
    data["citation_ids"] = [
        "invalid-citation",
    ]

    with pytest.raises(ValidationError):
        IncidentAssessment(**data)


def test_incident_assessment_rejects_duplicate_citations() -> None:
    data = make_assessment_data()
    data["citation_ids"] = [
        "RB-DB-001#diagnosis",
        "RB-DB-001#diagnosis",
    ]

    with pytest.raises(
        ValidationError,
        match="citation IDs must be unique",
    ):
        IncidentAssessment(**data)