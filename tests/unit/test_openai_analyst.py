from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)
from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.openai_analyst import (
    INCIDENT_ANALYST_INSTRUCTIONS,
    OpenAIIncidentAnalyst,
)
from apps.metadata_service.services.runbook_loader import (
    load_runbooks,
)


def make_context() -> tuple[
    IncidentEvidence,
    list[RetrievedRunbookSection],
]:
    incident = load_incidents()["INC-DB-001"]

    section = next(
        section
        for section in load_runbooks()
        if section.citation_id == "RB-DB-001#diagnosis"
    )

    retrieved_sections = [
        RetrievedRunbookSection(
            section=section,
            score=0.91,
        )
    ]

    return incident, retrieved_sections


def make_assessment() -> IncidentAssessment:
    return IncidentAssessment(
        incident_id="INC-DB-001",
        root_cause=(
            "Database connections are not being released."
        ),
        supporting_evidence=[
            "The connection pool is at maximum capacity.",
        ],
        recommended_actions=[
            "Roll back the recent deployment.",
        ],
        verification_steps=[
            "Verify that connection waiters return to zero.",
        ],
        confidence=0.91,
        citation_ids=[
            "RB-DB-001#diagnosis",
        ],
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_openai_analyst_returns_parsed_assessment() -> None:
    incident, retrieved_sections = make_context()
    expected_assessment = make_assessment()

    parse_response = AsyncMock(
        return_value=SimpleNamespace(
            output_parsed=expected_assessment,
        )
    )

    client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=parse_response,
        )
    )

    analyst = OpenAIIncidentAnalyst(
        client=client,
        model="gpt-analysis-test",
    )

    assessment = await analyst.analyze(
        incident=incident,
        retrieved_sections=retrieved_sections,
    )

    assert assessment == expected_assessment

    parse_response.assert_awaited_once()

    request = parse_response.await_args.kwargs

    assert request["model"] == "gpt-analysis-test"
    assert request["reasoning"] == {
        "effort": "medium",
    }
    assert request["instructions"] == (
        INCIDENT_ANALYST_INSTRUCTIONS
    )
    assert request["text_format"] is IncidentAssessment
    assert request["store"] is False
    assert "INC-DB-001" in request["input"]
    assert "RB-DB-001#diagnosis" in request["input"]


@pytest.mark.anyio
async def test_openai_analyst_rejects_missing_assessment() -> None:
    incident, retrieved_sections = make_context()

    parse_response = AsyncMock(
        return_value=SimpleNamespace(
            output_parsed=None,
        )
    )

    client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=parse_response,
        )
    )

    analyst = OpenAIIncidentAnalyst(
        client=client,
        model="gpt-analysis-test",
    )

    with pytest.raises(
        ValueError,
        match="did not contain a parsed",
    ):
        await analyst.analyze(
            incident=incident,
            retrieved_sections=retrieved_sections,
        )


@pytest.mark.anyio
async def test_openai_analyst_rejects_empty_context() -> None:
    incident, _ = make_context()

    parse_response = AsyncMock()

    client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=parse_response,
        )
    )

    analyst = OpenAIIncidentAnalyst(
        client=client,
        model="gpt-analysis-test",
    )

    with pytest.raises(
        ValueError,
        match="At least one retrieved section",
    ):
        await analyst.analyze(
            incident=incident,
            retrieved_sections=[],
        )

    parse_response.assert_not_awaited()