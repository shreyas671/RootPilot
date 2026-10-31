import pytest

from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.react import (
    CheckServiceHealthAction,
    GetRecentDeploymentsAction,
    QueryMetricsAction,
    SearchLogsAction,
    SearchRunbooksAction,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.diagnostic_tools import (
    IncidentDiagnosticToolkit,
)
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.runbook_loader import (
    load_runbooks,
)


class FakeRetriever:
    def __init__(
        self,
        results: list[RetrievedRunbookSection],
    ) -> None:
        self.results = results
        self.searches: list[tuple[str, int]] = []

    async def retrieve(
        self,
        incident: IncidentEvidence,
        limit: int = 3,
    ) -> list[RetrievedRunbookSection]:
        return self.results[:limit]

    async def search(
        self,
        query: str,
        limit: int = 3,
    ) -> list[RetrievedRunbookSection]:
        self.searches.append((query, limit))
        return self.results[:limit]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def make_toolkit() -> tuple[
    IncidentDiagnosticToolkit,
    FakeRetriever,
]:
    section = next(
        section
        for section in load_runbooks()
        if section.citation_id == "RB-DB-001#diagnosis"
    )
    retriever = FakeRetriever(
        [
            RetrievedRunbookSection(
                section=section,
                score=0.91,
            )
        ]
    )
    return IncidentDiagnosticToolkit(retriever), retriever


@pytest.mark.anyio
async def test_diagnostic_tools_expose_fixture_evidence() -> None:
    incident = load_incidents()["INC-DB-001"]
    toolkit, _ = make_toolkit()

    metric = await toolkit.execute(
        incident,
        QueryMetricsAction(
            tool="query_metrics",
            service="checkout-api",
            metric="db_pool_waiters",
            time_range="30m",
        ),
    )
    logs = await toolkit.execute(
        incident,
        SearchLogsAction(
            tool="search_logs",
            service="checkout-api",
            pattern="pool reached maximum",
            time_range="30m",
        ),
    )
    deployments = await toolkit.execute(
        incident,
        GetRecentDeploymentsAction(
            tool="get_recent_deployments",
            service="checkout-api",
            time_range="2h",
        ),
    )
    health = await toolkit.execute(
        incident,
        CheckServiceHealthAction(
            tool="check_service_health",
            service="postgres",
        ),
    )

    assert "46 requests" in metric.observation.summary
    assert metric.observation.evidence_ids == [
        "metric:checkout-api:db_pool_waiters"
    ]
    assert "active=20" in logs.observation.summary
    assert "v1.14.0" in deployments.observation.summary
    assert "reachable=true" in health.observation.summary
    assert "SELECT 1" in health.observation.summary


@pytest.mark.anyio
async def test_runbook_tool_uses_targeted_query() -> None:
    incident = load_incidents()["INC-DB-001"]
    toolkit, retriever = make_toolkit()
    result = await toolkit.execute(
        incident,
        SearchRunbooksAction(
            tool="search_runbooks",
            query="connection pool exhaustion recovery",
            limit=2,
        ),
    )

    assert retriever.searches == [
        ("connection pool exhaustion recovery", 2)
    ]
    assert result.retrieved_sections[0].section.citation_id == (
        "RB-DB-001#diagnosis"
    )


@pytest.mark.anyio
async def test_health_tool_rejects_unregistered_service() -> None:
    incident = load_incidents()["INC-DB-001"]
    toolkit, _ = make_toolkit()
    result = await toolkit.execute(
        incident,
        CheckServiceHealthAction(
            tool="check_service_health",
            service="unregistered-service",
        ),
    )

    assert result.observation.result_count == 0
    assert result.observation.evidence_ids == []
    assert "No allowlisted" in result.observation.summary
