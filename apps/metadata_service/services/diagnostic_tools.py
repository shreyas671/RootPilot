from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from typing import Protocol

from langsmith import traceable

from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.react import (
    CheckServiceHealthAction,
    GetRecentDeploymentsAction,
    QueryMetricsAction,
    ReactAction,
    SearchLogsAction,
    SearchRunbooksAction,
    ToolObservation,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.retriever import (
    RunbookRetriever,
)

TIME_RANGE_MINUTES = {
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "6h": 360,
    "24h": 1440,
}


@dataclass(frozen=True)
class ToolExecutionResult:
    observation: ToolObservation
    retrieved_sections: list[RetrievedRunbookSection]


class DiagnosticToolkit(Protocol):
    async def execute(
        self,
        incident: IncidentEvidence,
        action: ReactAction,
    ) -> ToolExecutionResult:
        ...


def _short_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def _matches_service(
    requested: str,
    available: str,
) -> bool:
    return requested.strip().casefold() == available.casefold()


class IncidentDiagnosticToolkit:
    """Read-only diagnostic tools backed by incident evidence."""

    def __init__(
        self,
        retriever: RunbookRetriever,
        minimum_relevance_score: float = 0.0,
        max_log_results: int = 20,
    ) -> None:
        self._retriever = retriever
        self._minimum_relevance_score = (
            minimum_relevance_score
        )
        self._max_log_results = max_log_results

    @traceable(
        name="rootpilot_react_tool",
        run_type="tool",
        tags=["rootpilot", "react", "tool"],
    )
    async def execute(
        self,
        incident: IncidentEvidence,
        action: ReactAction,
    ) -> ToolExecutionResult:
        if isinstance(action, QueryMetricsAction):
            return self._query_metrics(incident, action)
        if isinstance(action, SearchLogsAction):
            return self._search_logs(incident, action)
        if isinstance(action, GetRecentDeploymentsAction):
            return self._get_recent_deployments(
                incident,
                action,
            )
        if isinstance(action, CheckServiceHealthAction):
            return self._check_service_health(
                incident,
                action,
            )
        if isinstance(action, SearchRunbooksAction):
            return await self._search_runbooks(action)

        raise ValueError(
            f"Action {action.tool} is not an executable tool"
        )

    def _query_metrics(
        self,
        incident: IncidentEvidence,
        action: QueryMetricsAction,
    ) -> ToolExecutionResult:
        if not _matches_service(
            action.service,
            incident.service,
        ):
            return self._empty(
                action.tool,
                f"No metric source is registered for service "
                f"{action.service}.",
                is_error=True,
            )

        requested = action.metric.casefold()
        matches = [
            metric
            for metric in incident.metrics
            if requested == metric.name.casefold()
            or requested in metric.name.casefold()
            or metric.name.casefold() in requested
        ]

        if not matches:
            return self._empty(
                action.tool,
                f"Metric {action.metric} was not available for "
                f"{incident.service} in {action.time_range}.",
            )

        evidence_ids = [
            f"metric:{incident.service}:{metric.name}"
            for metric in matches
        ]
        values = "; ".join(
            f"{metric.name}={metric.value:g} {metric.unit}"
            for metric in matches
        )
        return ToolExecutionResult(
            observation=ToolObservation(
                tool=action.tool,
                summary=(
                    f"Metric snapshot for {incident.service} "
                    f"(requested window {action.time_range}): "
                    f"{values}."
                ),
                evidence_ids=evidence_ids,
                result_count=len(matches),
            ),
            retrieved_sections=[],
        )

    def _search_logs(
        self,
        incident: IncidentEvidence,
        action: SearchLogsAction,
    ) -> ToolExecutionResult:
        if not _matches_service(
            action.service,
            incident.service,
        ):
            return self._empty(
                action.tool,
                f"No log source is registered for service "
                f"{action.service}.",
                is_error=True,
            )

        cutoff = incident.started_at - timedelta(
            minutes=TIME_RANGE_MINUTES[action.time_range]
        )
        terms = [
            term
            for term in action.pattern.casefold().split()
            if term
        ]
        matches = [
            entry
            for entry in incident.logs
            if entry.timestamp >= cutoff
            and all(
                term in entry.message.casefold()
                for term in terms
            )
        ][: self._max_log_results]

        if not matches:
            return self._empty(
                action.tool,
                f"No logs matched {action.pattern!r} for "
                f"{incident.service} in {action.time_range}.",
            )

        evidence_ids = [
            "log:"
            + _short_hash(
                f"{entry.timestamp.isoformat()}:{entry.message}"
            )
            for entry in matches
        ]
        rendered = "; ".join(
            f"{entry.timestamp.isoformat()} {entry.level}: "
            f"{entry.message}"
            for entry in matches
        )
        return ToolExecutionResult(
            observation=ToolObservation(
                tool=action.tool,
                summary=f"Matched log entries: {rendered}",
                evidence_ids=evidence_ids,
                result_count=len(matches),
            ),
            retrieved_sections=[],
        )

    def _get_recent_deployments(
        self,
        incident: IncidentEvidence,
        action: GetRecentDeploymentsAction,
    ) -> ToolExecutionResult:
        if not _matches_service(
            action.service,
            incident.service,
        ):
            return self._empty(
                action.tool,
                f"No deployment source is registered for service "
                f"{action.service}.",
                is_error=True,
            )

        cutoff = incident.started_at - timedelta(
            minutes=TIME_RANGE_MINUTES[action.time_range]
        )
        changes = [
            change
            for change in incident.recent_changes
            if change.timestamp >= cutoff
        ]

        if not changes:
            return self._empty(
                action.tool,
                f"No deployments or changes were recorded for "
                f"{incident.service} in {action.time_range}.",
            )

        evidence_ids = [
            "change:"
            + _short_hash(
                f"{change.timestamp.isoformat()}:"
                f"{change.description}"
            )
            for change in changes
        ]
        rendered = "; ".join(
            f"{change.timestamp.isoformat()}: "
            f"{change.description}"
            for change in changes
        )
        return ToolExecutionResult(
            observation=ToolObservation(
                tool=action.tool,
                summary=f"Recent deployments or changes: {rendered}",
                evidence_ids=evidence_ids,
                result_count=len(changes),
            ),
            retrieved_sections=[],
        )

    def _check_service_health(
        self,
        incident: IncidentEvidence,
        action: CheckServiceHealthAction,
    ) -> ToolExecutionResult:
        matches = [
            check
            for check in incident.service_health
            if _matches_service(action.service, check.service)
        ]

        if not matches:
            return self._empty(
                action.tool,
                f"No allowlisted health check evidence exists for "
                f"service {action.service}.",
                is_error=True,
            )

        evidence_ids = [
            f"health:{check.service}:"
            + _short_hash(check.observed_at.isoformat())
            for check in matches
        ]
        rendered = "; ".join(
            f"{check.service} reachable={str(check.reachable).lower()} "
            f"latency={check.latency_ms:g} ms via {check.check}"
            for check in matches
        )
        return ToolExecutionResult(
            observation=ToolObservation(
                tool=action.tool,
                summary=f"Health check observation: {rendered}.",
                evidence_ids=evidence_ids,
                result_count=len(matches),
            ),
            retrieved_sections=[],
        )

    async def _search_runbooks(
        self,
        action: SearchRunbooksAction,
    ) -> ToolExecutionResult:
        candidates = await self._retriever.search(
            query=action.query,
            limit=action.limit,
        )
        matches = [
            result
            for result in candidates
            if result.score >= self._minimum_relevance_score
        ]

        if not matches:
            return self._empty(
                action.tool,
                "No runbook section met the minimum relevance "
                f"score for query {action.query!r}.",
            )

        evidence_ids = [
            f"runbook:{result.section.citation_id}"
            for result in matches
        ]
        rendered = "; ".join(
            f"{result.section.citation_id} "
            f"({result.section.section_title}, "
            f"score={result.score:.4f})"
            for result in matches
        )
        return ToolExecutionResult(
            observation=ToolObservation(
                tool=action.tool,
                summary=f"Retrieved runbook sections: {rendered}.",
                evidence_ids=evidence_ids,
                result_count=len(matches),
            ),
            retrieved_sections=matches,
        )

    @staticmethod
    def _empty(
        tool: str,
        summary: str,
        is_error: bool = False,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            observation=ToolObservation(
                tool=tool,
                summary=summary,
                result_count=0,
                is_error=is_error,
            ),
            retrieved_sections=[],
        )
