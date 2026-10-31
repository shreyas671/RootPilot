from collections import deque

import pytest

from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)
from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.react import (
    CheckServiceHealthAction,
    FinalizeAssessmentAction,
    GetRecentDeploymentsAction,
    QueryMetricsAction,
    ReactDecision,
    RequestAdditionalEvidenceAction,
    SearchLogsAction,
    SearchRunbooksAction,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.react_investigation_graph import (
    InsufficientEvidenceError,
    ReActGraphConfig,
    ReActLimitReachedError,
    build_react_investigation_graph,
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
        return self.results[:limit]


class FakeAgent:
    def __init__(
        self,
        decisions: list[ReactDecision],
        assessments: list[IncidentAssessment],
    ) -> None:
        self.decisions = deque(decisions)
        self.assessments = deque(assessments)
        self.analysis_calls = 0

    async def decide(self, **_: object) -> ReactDecision:
        return self.decisions.popleft()

    async def analyze_react(
        self,
        **_: object,
    ) -> IncidentAssessment:
        self.analysis_calls += 1
        return self.assessments.popleft()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def make_section() -> RetrievedRunbookSection:
    section = next(
        section
        for section in load_runbooks()
        if section.citation_id == "RB-DB-001#diagnosis"
    )
    return RetrievedRunbookSection(
        section=section,
        score=0.91,
    )


def make_assessment(
    citation_id: str = "RB-DB-001#diagnosis",
) -> IncidentAssessment:
    return IncidentAssessment(
        incident_id="INC-DB-001",
        root_cause=(
            "The checkout-api connection pool is exhausted."
        ),
        supporting_evidence=[
            "All configured connections are active.",
            "Requests are waiting for a connection.",
        ],
        recommended_actions=[
            "Restore connection capacity using the runbook.",
        ],
        verification_steps=[
            "Verify that connection waiters return to zero.",
        ],
        confidence=0.94,
        citation_ids=[citation_id],
    )


def decision(action: object) -> ReactDecision:
    return ReactDecision(
        hypothesis="Connection pool exhaustion is likely.",
        rationale="Collect another independent observation.",
        action=action,
    )


def successful_decisions() -> list[ReactDecision]:
    return [
        decision(
            QueryMetricsAction(
                tool="query_metrics",
                service="checkout-api",
                metric="db_pool_active_connections",
                time_range="30m",
            )
        ),
        decision(
            QueryMetricsAction(
                tool="query_metrics",
                service="checkout-api",
                metric="db_pool_waiters",
                time_range="30m",
            )
        ),
        decision(
            SearchRunbooksAction(
                tool="search_runbooks",
                query="database connection pool exhaustion",
                limit=3,
            )
        ),
        decision(
            FinalizeAssessmentAction(
                tool="finalize_assessment",
                evidence_ids=[
                    "metric:checkout-api:db_pool_active_connections",
                    "metric:checkout-api:db_pool_waiters",
                ],
            )
        ),
    ]


@pytest.mark.anyio
async def test_react_graph_runs_tools_and_finalizes() -> None:
    agent = FakeAgent(
        successful_decisions(),
        [make_assessment()],
    )
    graph = build_react_investigation_graph(
        retriever=FakeRetriever([make_section()]),
        planner=agent,
        analyst=agent,
    )

    result = await graph.ainvoke(
        {"incident": load_incidents()["INC-DB-001"]}
    )

    assert result["assessment_validated"] is True
    assert result["termination_reason"] == "model_finished"
    assert result["iteration_count"] == 4
    assert result["tool_call_count"] == 3
    assert [step.tool for step in result["react_steps"]] == [
        "query_metrics",
        "query_metrics",
        "search_runbooks",
        "finalize_assessment",
    ]


@pytest.mark.anyio
async def test_react_graph_repairs_unsupported_citation() -> None:
    agent = FakeAgent(
        successful_decisions(),
        [
            make_assessment("RB-DB-999#invented"),
            make_assessment(),
        ],
    )
    graph = build_react_investigation_graph(
        retriever=FakeRetriever([make_section()]),
        planner=agent,
        analyst=agent,
    )

    result = await graph.ainvoke(
        {"incident": load_incidents()["INC-DB-001"]}
    )

    assert result["assessment_validated"] is True
    assert result["assessment_repair_count"] == 1
    assert agent.analysis_calls == 2


@pytest.mark.anyio
async def test_react_graph_repairs_schema_validation_error() -> None:
    class SchemaRepairingAgent(FakeAgent):
        async def analyze_react(
            self,
            **_: object,
        ) -> IncidentAssessment:
            self.analysis_calls += 1
            if self.analysis_calls == 1:
                IncidentAssessment(
                    incident_id="INC-DB-001",
                    root_cause="Pool exhaustion",
                    supporting_evidence=["Pool is full."],
                    recommended_actions=["Restore capacity."],
                    verification_steps=["Check waiters."],
                    confidence=0.9,
                    citation_ids=[
                        "RB-DB-001#diagnosis",
                        "RB-DB-001#diagnosis",
                    ],
                )
            return make_assessment()

    agent = SchemaRepairingAgent(
        successful_decisions(),
        [],
    )
    graph = build_react_investigation_graph(
        retriever=FakeRetriever([make_section()]),
        planner=agent,
        analyst=agent,
    )

    result = await graph.ainvoke(
        {"incident": load_incidents()["INC-DB-001"]}
    )

    assert result["assessment_validated"] is True
    assert result["assessment_repair_count"] == 1
    assert agent.analysis_calls == 2


@pytest.mark.anyio
async def test_react_graph_finalizes_at_iteration_limit() -> None:
    agent = FakeAgent(
        successful_decisions()[:3],
        [make_assessment()],
    )
    graph = build_react_investigation_graph(
        retriever=FakeRetriever([make_section()]),
        planner=agent,
        analyst=agent,
        config=ReActGraphConfig(max_iterations=3),
    )

    result = await graph.ainvoke(
        {"incident": load_incidents()["INC-DB-001"]}
    )

    assert result["assessment_validated"] is True
    assert result["termination_reason"] == "max_iterations"
    assert result["tool_call_count"] == 3


@pytest.mark.anyio
async def test_react_explores_other_tools_after_empty_results() -> None:
    tls_incident = load_incidents()["INC-TLS-001"]
    tls_section = next(
        section
        for section in load_runbooks()
        if section.citation_id == "RB-TLS-001#signals"
    )
    metric_id = (
        "metric:webhook-gateway:certificate_days_remaining"
    )
    decisions = [
        decision(
            GetRecentDeploymentsAction(
                tool="get_recent_deployments",
                service="webhook-gateway",
                time_range="2h",
            )
        ),
        decision(
            SearchLogsAction(
                tool="search_logs",
                service="webhook-gateway",
                pattern="unrelated database timeout",
                time_range="30m",
            )
        ),
        decision(
            QueryMetricsAction(
                tool="query_metrics",
                service="webhook-gateway",
                metric="certificate_days_remaining",
                time_range="30m",
            )
        ),
        decision(
            CheckServiceHealthAction(
                tool="check_service_health",
                service="webhook-gateway",
            )
        ),
        decision(
            SearchRunbooksAction(
                tool="search_runbooks",
                query="expired TLS certificate",
                limit=3,
            )
        ),
    ]

    class TLSAgent(FakeAgent):
        async def decide(self, **kwargs: object) -> ReactDecision:
            if self.decisions:
                return self.decisions.popleft()
            observations = kwargs["observations"]
            health_evidence_id = next(
                evidence_id
                for observation in observations
                for evidence_id in observation.evidence_ids
                if evidence_id.startswith("health:")
            )
            return decision(
                FinalizeAssessmentAction(
                    tool="finalize_assessment",
                    evidence_ids=[metric_id, health_evidence_id],
                )
            )

    assessment = IncidentAssessment(
        incident_id="INC-TLS-001",
        root_cause="The partner TLS certificate expired.",
        supporting_evidence=[
            "The certificate has zero days remaining.",
            "The gateway itself remains healthy.",
        ],
        recommended_actions=["Deploy a valid certificate."],
        verification_steps=["Verify TLS handshakes recover."],
        confidence=0.96,
        citation_ids=["RB-TLS-001#signals"],
    )
    agent = TLSAgent(decisions, [assessment])
    graph = build_react_investigation_graph(
        retriever=FakeRetriever(
            [
                RetrievedRunbookSection(
                    section=tls_section,
                    score=0.95,
                )
            ]
        ),
        planner=agent,
        analyst=agent,
        config=ReActGraphConfig(no_progress_limit=2),
    )

    result = await graph.ainvoke({"incident": tls_incident})

    assert result["assessment_validated"] is True
    assert result["iteration_count"] == 6
    assert result["react_steps"][0].new_evidence_count == 0
    assert result["react_steps"][1].new_evidence_count == 0


@pytest.mark.anyio
async def test_react_graph_stops_for_requested_evidence() -> None:
    agent = FakeAgent(
        [
            decision(
                RequestAdditionalEvidenceAction(
                    tool="request_additional_evidence",
                    evidence_needed=["database reachability"],
                    reason="No health check is available.",
                )
            )
        ],
        [],
    )
    graph = build_react_investigation_graph(
        retriever=FakeRetriever([make_section()]),
        planner=agent,
        analyst=agent,
    )

    with pytest.raises(
        InsufficientEvidenceError,
        match="database reachability",
    ):
        await graph.ainvoke(
            {"incident": load_incidents()["INC-DB-001"]}
        )


@pytest.mark.anyio
async def test_duplicate_action_triggers_no_progress_stop() -> None:
    repeated = QueryMetricsAction(
        tool="query_metrics",
        service="checkout-api",
        metric="db_pool_waiters",
        time_range="30m",
    )
    agent = FakeAgent(
        [decision(repeated), decision(repeated)],
        [],
    )
    graph = build_react_investigation_graph(
        retriever=FakeRetriever([make_section()]),
        planner=agent,
        analyst=agent,
        config=ReActGraphConfig(no_progress_limit=1),
    )

    with pytest.raises(
        ReActLimitReachedError,
        match="no-progress limit",
    ):
        await graph.ainvoke(
            {"incident": load_incidents()["INC-DB-001"]}
        )
