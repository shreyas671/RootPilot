import pytest

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


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_graph_retrieves_runbook_context() -> None:
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

    retriever = FakeRunbookRetriever(
        results=[retrieved_section],
    )

    graph = build_investigation_graph(
        retriever=retriever,
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
    assert retriever.calls == [
        (
            "INC-DB-001",
            2,
        )
    ]


def test_graph_rejects_invalid_retrieval_limit() -> None:
    retriever = FakeRunbookRetriever(results=[])

    with pytest.raises(
        ValueError,
        match="Retrieval limit must be at least 1",
    ):
        build_investigation_graph(
            retriever=retriever,
            retrieval_limit=0,
        )