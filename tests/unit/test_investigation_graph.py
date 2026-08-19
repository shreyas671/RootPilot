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
from apps.metadata_service.services.investigation_graph import (
    NoRelevantRunbookContextError,
    build_investigation_graph,
)
from apps.metadata_service.services.runbook_loader import (
    load_runbooks,
)


class FakeRunbookRetriever:
    def __init__(
        self,
        results: list[RetrievedRunbookSection],
    ) -> None:
        self._results = results
        self.calls: list[tuple[str, int]] = []

    async def retrieve(
        self,
        incident: IncidentEvidence,
        limit: int = 3,
    ) -> list[RetrievedRunbookSection]:
        self.calls.append(
            (
                incident.incident_id,
                limit,
            )
        )

        return self._results[:limit]


class FakeIncidentAnalyst:
    def __init__(
        self,
        assessment: IncidentAssessment,
    ) -> None:
        self._assessment = assessment
        self.calls: list[
            tuple[str, list[str]]
        ] = []

    async def analyze(
        self,
        incident: IncidentEvidence,
        retrieved_sections: list[
            RetrievedRunbookSection
        ],
    ) -> IncidentAssessment:
        self.calls.append(
            (
                incident.incident_id,
                [
                    result.section.citation_id
                    for result in retrieved_sections
                ],
            )
        )

        return self._assessment


def make_assessment(
    incident_id: str,
    citation_id: str,
) -> IncidentAssessment:
    return IncidentAssessment(
        incident_id=incident_id,
        root_cause=(
            "Database connections are not being released."
        ),
        supporting_evidence=[
            "Active connections equal the pool maximum.",
        ],
        recommended_actions=[
            "Roll back the recent deployment.",
        ],
        verification_steps=[
            "Verify that connection waiters return to zero.",
        ],
        confidence=0.91,
        citation_ids=[citation_id],
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_graph_generates_incident_assessment() -> None:
    incident = load_incidents()["INC-DB-001"]

    section = next(
        section
        for section in load_runbooks()
        if section.citation_id == "RB-DB-001#diagnosis"
    )

    retrieved_section = RetrievedRunbookSection(
        section=section,
        score=0.91,
    )

    assessment = make_assessment(
        incident_id=incident.incident_id,
        citation_id=section.citation_id,
    )

    retriever = FakeRunbookRetriever(
        results=[retrieved_section],
    )
    analyst = FakeIncidentAnalyst(
        assessment=assessment,
    )

    graph = build_investigation_graph(
        retriever=retriever,
        analyst=analyst,
        retrieval_limit=2,
    )

    result = await graph.ainvoke(
        {
            "incident": incident,
        }
    )

    assert result["incident"] == incident
    assert result["retrieved_sections"] == [
        retrieved_section,
    ]
    assert result["assessment"] == assessment
    assert result["assessment_validated"] is True

    assert retriever.calls == [
        (
            "INC-DB-001",
            2,
        )
    ]
    assert analyst.calls == [
        (
            "INC-DB-001",
            [
                "RB-DB-001#diagnosis",
            ],
        )
    ]


def test_graph_rejects_invalid_retrieval_limit() -> None:
    retriever = FakeRunbookRetriever(results=[])

    analyst = FakeIncidentAnalyst(
        assessment=make_assessment(
            incident_id="INC-DB-001",
            citation_id="RB-DB-001#diagnosis",
        )
    )

    with pytest.raises(
        ValueError,
        match="Retrieval limit must be at least 1",
    ):
        build_investigation_graph(
            retriever=retriever,
            analyst=analyst,
            retrieval_limit=0,
        )


@pytest.mark.parametrize(
    "minimum_relevance_score",
    [-1.01, 1.01],
)
def test_graph_rejects_invalid_minimum_score(
    minimum_relevance_score: float,
) -> None:
    retriever = FakeRunbookRetriever(results=[])
    analyst = FakeIncidentAnalyst(
        assessment=make_assessment(
            incident_id="INC-DB-001",
            citation_id="RB-DB-001#diagnosis",
        )
    )

    with pytest.raises(
        ValueError,
        match="Minimum relevance score must be between",
    ):
        build_investigation_graph(
            retriever=retriever,
            analyst=analyst,
            minimum_relevance_score=(
                minimum_relevance_score
            ),
        )


@pytest.mark.anyio
async def test_graph_stops_when_context_is_not_relevant() -> None:
    incident = load_incidents()["INC-DB-001"]
    section = next(
        section
        for section in load_runbooks()
        if section.citation_id == "RB-DB-001#diagnosis"
    )
    analyst = FakeIncidentAnalyst(
        assessment=make_assessment(
            incident_id=incident.incident_id,
            citation_id=section.citation_id,
        )
    )
    graph = build_investigation_graph(
        retriever=FakeRunbookRetriever(
            results=[
                RetrievedRunbookSection(
                    section=section,
                    score=0.24,
                )
            ],
        ),
        analyst=analyst,
        minimum_relevance_score=0.25,
    )

    with pytest.raises(
        NoRelevantRunbookContextError,
        match="No runbook section met",
    ):
        await graph.ainvoke(
            {
                "incident": incident,
            }
        )

    assert analyst.calls == []

@pytest.mark.anyio
async def test_graph_rejects_assessment_for_different_incident() -> None:
    incident = load_incidents()["INC-DB-001"]

    section = next(
        section
        for section in load_runbooks()
        if section.citation_id == "RB-DB-001#diagnosis"
    )

    retrieved_section = RetrievedRunbookSection(
        section=section,
        score=0.91,
    )

    assessment = make_assessment(
        incident_id="INC-KAFKA-001",
        citation_id=section.citation_id,
    )

    graph = build_investigation_graph(
        retriever=FakeRunbookRetriever(
            results=[retrieved_section],
        ),
        analyst=FakeIncidentAnalyst(
            assessment=assessment,
        ),
    )

    with pytest.raises(
        ValueError,
        match="Assessment incident ID does not match",
    ):
        await graph.ainvoke(
            {
                "incident": incident,
            }
        )

@pytest.mark.anyio
async def test_graph_rejects_citation_that_was_not_retrieved() -> None:
    incident = load_incidents()["INC-DB-001"]

    section = next(
        section
        for section in load_runbooks()
        if section.citation_id == "RB-DB-001#diagnosis"
    )

    retrieved_section = RetrievedRunbookSection(
        section=section,
        score=0.91,
    )

    assessment = make_assessment(
        incident_id=incident.incident_id,
        citation_id="RB-KAFKA-001#diagnosis",
    )

    graph = build_investigation_graph(
        retriever=FakeRunbookRetriever(
            results=[retrieved_section],
        ),
        analyst=FakeIncidentAnalyst(
            assessment=assessment,
        ),
    )

    with pytest.raises(
        ValueError,
        match="citations that were not retrieved",
    ):
        await graph.ainvoke(
            {
                "incident": incident,
            }
        )
