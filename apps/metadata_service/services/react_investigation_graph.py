import asyncio
import json
import time
from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from apps.metadata_service.schemas.investigation import (
    InvestigationState,
)
from apps.metadata_service.schemas.react import (
    FinalizeAssessmentAction,
    InvestigationStep,
    RequestAdditionalEvidenceAction,
    ToolObservation,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.diagnostic_tools import (
    DiagnosticToolkit,
    IncidentDiagnosticToolkit,
)
from apps.metadata_service.services.react_agent import (
    ReActAssessmentAnalyst,
    ReActPlanner,
)
from apps.metadata_service.services.retriever import (
    RunbookRetriever,
)


class InsufficientEvidenceError(ValueError):
    pass


class ReActLimitReachedError(ValueError):
    pass


class ReActAssessmentValidationError(ValueError):
    pass


EVIDENCE_TOOL_NAMES = {
    "query_metrics",
    "search_logs",
    "get_recent_deployments",
    "check_service_health",
    "search_runbooks",
}


@dataclass(frozen=True)
class ReActGraphConfig:
    max_iterations: int = 8
    max_tool_calls: int = 10
    no_progress_limit: int = 2
    max_tool_errors: int = 3
    max_runtime_seconds: float = 180.0
    max_context_sections: int = 10
    min_evidence_items: int = 2
    max_repair_attempts: int = 2

    def validate(self) -> None:
        values = {
            "max_iterations": self.max_iterations,
            "max_tool_calls": self.max_tool_calls,
            "no_progress_limit": self.no_progress_limit,
            "max_tool_errors": self.max_tool_errors,
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_context_sections": self.max_context_sections,
            "min_evidence_items": self.min_evidence_items,
        }
        for name, value in values.items():
            if value < 1:
                raise ValueError(f"{name} must be at least 1")
        if self.max_repair_attempts < 0:
            raise ValueError(
                "max_repair_attempts cannot be negative"
            )


def _merge_sections(
    existing: list[RetrievedRunbookSection],
    additions: list[RetrievedRunbookSection],
    limit: int,
) -> list[RetrievedRunbookSection]:
    by_citation = {
        item.section.citation_id: item
        for item in existing
    }
    for item in additions:
        current = by_citation.get(item.section.citation_id)
        if current is None or item.score > current.score:
            by_citation[item.section.citation_id] = item
    return sorted(
        by_citation.values(),
        key=lambda item: (
            -item.score,
            item.section.citation_id,
        ),
    )[:limit]


def _diagnostic_evidence_ids(
    state: InvestigationState,
) -> set[str]:
    return {
        evidence_id
        for evidence_id in state.get(
            "observed_evidence_ids",
            [],
        )
        if not evidence_id.startswith("runbook:")
    }


def _has_sufficient_evidence(
    state: InvestigationState,
    config: ReActGraphConfig,
) -> bool:
    return (
        len(_diagnostic_evidence_ids(state))
        >= config.min_evidence_items
        and bool(state.get("retrieved_sections"))
    )


def _has_unexplored_evidence_tools(
    state: InvestigationState,
) -> bool:
    attempted = {
        step.tool
        for step in state.get("react_steps", [])
    }
    return bool(EVIDENCE_TOOL_NAMES - attempted)


def build_react_investigation_graph(
    retriever: RunbookRetriever,
    planner: ReActPlanner,
    analyst: ReActAssessmentAnalyst,
    minimum_relevance_score: float = 0.0,
    config: ReActGraphConfig | None = None,
    diagnostic_toolkit: DiagnosticToolkit | None = None,
) -> CompiledStateGraph:
    graph_config = config or ReActGraphConfig()
    graph_config.validate()

    if not -1.0 <= minimum_relevance_score <= 1.0:
        raise ValueError(
            "Minimum relevance score must be between "
            "-1.0 and 1.0"
        )

    toolkit = diagnostic_toolkit or IncidentDiagnosticToolkit(
        retriever=retriever,
        minimum_relevance_score=minimum_relevance_score,
    )

    def remaining_runtime(
        state: InvestigationState,
    ) -> float:
        elapsed = time.monotonic() - state.get(
            "react_started_at",
            time.monotonic(),
        )
        return max(
            0.001,
            graph_config.max_runtime_seconds - elapsed,
        )

    def initialize(
        state: InvestigationState,
    ) -> dict[str, object]:
        return {
            "retrieved_sections": [],
            "observations": [],
            "react_steps": [],
            "observed_evidence_ids": [],
            "executed_action_fingerprints": [],
            "iteration_count": 0,
            "tool_call_count": 0,
            "tool_error_count": 0,
            "no_progress_count": 0,
            "duplicate_action_count": 0,
            "assessment_repair_count": 0,
            "validation_error": None,
            "assessment_validated": False,
            "assessment_generation_failed": False,
            "react_started_at": time.monotonic(),
        }

    async def choose_action(
        state: InvestigationState,
    ) -> dict[str, object]:
        iteration = state.get("iteration_count", 0) + 1
        try:
            async with asyncio.timeout(remaining_runtime(state)):
                decision = await planner.decide(
                    incident=state["incident"],
                    steps=state.get("react_steps", []),
                    observations=state.get("observations", []),
                    remaining_iterations=max(
                        0,
                        graph_config.max_iterations
                        - iteration
                        + 1,
                    ),
                    remaining_tool_calls=max(
                        0,
                        graph_config.max_tool_calls
                        - state.get("tool_call_count", 0),
                    ),
                    minimum_evidence_items=(
                        graph_config.min_evidence_items
                    ),
                    requires_runbook_context=True,
                )
        except TimeoutError as exc:
            raise ReActLimitReachedError(
                "ReAct investigation reached the runtime limit"
            ) from exc
        return {
            "current_decision": decision,
            "iteration_count": iteration,
        }

    def route_action(state: InvestigationState) -> str:
        action = state["current_decision"].action
        if isinstance(action, FinalizeAssessmentAction):
            return "finalize"
        if isinstance(
            action,
            RequestAdditionalEvidenceAction,
        ):
            return "request_additional_evidence"
        return "execute_tool"

    async def execute_tool(
        state: InvestigationState,
    ) -> dict[str, object]:
        decision = state["current_decision"]
        action = decision.action
        serialized_action = action.model_dump(mode="json")
        fingerprint = json.dumps(
            serialized_action,
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprints = state.get(
            "executed_action_fingerprints",
            [],
        )

        if fingerprint in fingerprints:
            observation = ToolObservation(
                tool=action.tool,
                summary=(
                    "Duplicate tool call blocked because the same "
                    "action and arguments were already executed."
                ),
                result_count=0,
            )
            result_sections: list[
                RetrievedRunbookSection
            ] = []
            tool_calls = state.get("tool_call_count", 0)
        else:
            try:
                async with asyncio.timeout(
                    remaining_runtime(state)
                ):
                    result = await toolkit.execute(
                        incident=state["incident"],
                        action=action,
                    )
            except TimeoutError as exc:
                raise ReActLimitReachedError(
                    "ReAct investigation reached the runtime "
                    "limit"
                ) from exc
            observation = result.observation
            result_sections = result.retrieved_sections
            fingerprints = [*fingerprints, fingerprint]
            tool_calls = state.get("tool_call_count", 0) + 1

        prior_evidence_ids = set(
            state.get("observed_evidence_ids", [])
        )
        new_evidence_ids = [
            evidence_id
            for evidence_id in observation.evidence_ids
            if evidence_id not in prior_evidence_ids
        ]
        all_evidence_ids = [
            *state.get("observed_evidence_ids", []),
            *new_evidence_ids,
        ]
        is_duplicate = fingerprint in state.get(
            "executed_action_fingerprints",
            [],
        )
        step = InvestigationStep(
            iteration=state["iteration_count"],
            tool=action.tool,
            hypothesis=decision.hypothesis,
            rationale=decision.rationale,
            arguments={
                key: value
                for key, value in serialized_action.items()
                if key != "tool"
            },
            observation=observation.summary,
            evidence_ids=observation.evidence_ids,
            new_evidence_count=len(new_evidence_ids),
            is_error=observation.is_error or is_duplicate,
        )
        return {
            "observations": [
                *state.get("observations", []),
                observation,
            ],
            "react_steps": [
                *state.get("react_steps", []),
                step,
            ],
            "observed_evidence_ids": all_evidence_ids,
            "executed_action_fingerprints": fingerprints,
            "retrieved_sections": _merge_sections(
                state.get("retrieved_sections", []),
                result_sections,
                graph_config.max_context_sections,
            ),
            "tool_call_count": tool_calls,
            "tool_error_count": (
                state.get("tool_error_count", 0)
                + int(observation.is_error)
            ),
            "no_progress_count": (
                0
                if new_evidence_ids
                else state.get("no_progress_count", 0) + 1
            ),
            "duplicate_action_count": (
                state.get("duplicate_action_count", 0) + 1
                if is_duplicate
                else 0
            ),
        }

    def prepare_finalize(
        state: InvestigationState,
    ) -> dict[str, object]:
        decision = state["current_decision"]
        action = decision.action
        if not isinstance(action, FinalizeAssessmentAction):
            raise TypeError("Expected finalize assessment action")

        observed = set(
            state.get("observed_evidence_ids", [])
        )
        unsupported = sorted(
            set(action.evidence_ids) - observed
        )
        selected_diagnostic_ids = {
            evidence_id
            for evidence_id in action.evidence_ids
            if not evidence_id.startswith("runbook:")
        }
        sufficient = _has_sufficient_evidence(
            state,
            graph_config,
        ) and (
            len(selected_diagnostic_ids)
            >= graph_config.min_evidence_items
        )
        if unsupported:
            observation_text = (
                "Finalization rejected because these evidence IDs "
                "were not observed: " + ", ".join(unsupported)
            )
        elif not sufficient:
            observation_text = (
                "Finalization rejected because at least "
                f"{graph_config.min_evidence_items} diagnostic "
                "evidence items and one relevant runbook section "
                "are required."
            )
        else:
            observation_text = (
                "Evidence threshold satisfied; generating the "
                "grounded incident assessment."
            )

        accepted = not unsupported and sufficient
        step = InvestigationStep(
            iteration=state["iteration_count"],
            tool=action.tool,
            hypothesis=decision.hypothesis,
            rationale=decision.rationale,
            arguments={
                "evidence_ids": action.evidence_ids,
            },
            observation=observation_text,
            evidence_ids=action.evidence_ids,
            new_evidence_count=0,
            is_error=not accepted,
        )
        update: dict[str, object] = {
            "react_steps": [
                *state.get("react_steps", []),
                step,
            ],
            "no_progress_count": (
                0
                if accepted
                else state.get("no_progress_count", 0) + 1
            ),
        }
        if accepted:
            update["termination_reason"] = "model_finished"
        return update

    def request_additional_evidence(
        state: InvestigationState,
    ) -> dict[str, object]:
        action = state["current_decision"].action
        if not isinstance(
            action,
            RequestAdditionalEvidenceAction,
        ):
            raise TypeError(
                "Expected request additional evidence action"
            )
        needed = ", ".join(action.evidence_needed)
        raise InsufficientEvidenceError(
            f"Additional evidence required: {needed}. "
            f"Reason: {action.reason}"
        )

    def route_after_progress(state: InvestigationState) -> str:
        elapsed = time.monotonic() - state.get(
            "react_started_at",
            time.monotonic(),
        )
        limits: list[tuple[bool, str]] = [
            (
                elapsed >= graph_config.max_runtime_seconds,
                "runtime_limit",
            ),
            (
                state.get("tool_error_count", 0)
                >= graph_config.max_tool_errors,
                "tool_error_limit",
            ),
            (
                (
                    state.get("duplicate_action_count", 0)
                    >= graph_config.no_progress_limit
                )
                or (
                    state.get("no_progress_count", 0)
                    >= graph_config.no_progress_limit
                    and not _has_unexplored_evidence_tools(
                        state
                    )
                ),
                "no_progress",
            ),
            (
                state.get("tool_call_count", 0)
                >= graph_config.max_tool_calls,
                "max_tool_calls",
            ),
            (
                state.get("iteration_count", 0)
                >= graph_config.max_iterations,
                "max_iterations",
            ),
        ]
        for reached, reason in limits:
            if reached:
                if _has_sufficient_evidence(state, graph_config):
                    return "prepare_limit_finalize"
                return f"stop_{reason}"

        if state.get("termination_reason") == "model_finished":
            return "generate_assessment"
        return "choose_action"

    def prepare_limit_finalize(
        state: InvestigationState,
    ) -> dict[str, object]:
        elapsed = time.monotonic() - state.get(
            "react_started_at",
            time.monotonic(),
        )
        if elapsed >= graph_config.max_runtime_seconds:
            reason = "runtime_limit"
        elif (
            state.get("tool_error_count", 0)
            >= graph_config.max_tool_errors
        ):
            reason = "tool_error_limit"
        elif (
            state.get("duplicate_action_count", 0)
            >= graph_config.no_progress_limit
            or (
                state.get("no_progress_count", 0)
                >= graph_config.no_progress_limit
                and not _has_unexplored_evidence_tools(state)
            )
        ):
            reason = "no_progress"
        elif (
            state.get("tool_call_count", 0)
            >= graph_config.max_tool_calls
        ):
            reason = "max_tool_calls"
        else:
            reason = "max_iterations"
        return {"termination_reason": reason}

    def stop_for_limit(
        state: InvestigationState,
    ) -> dict[str, object]:
        elapsed = time.monotonic() - state.get(
            "react_started_at",
            time.monotonic(),
        )
        if elapsed >= graph_config.max_runtime_seconds:
            reason = "runtime limit"
        elif (
            state.get("tool_error_count", 0)
            >= graph_config.max_tool_errors
        ):
            reason = "tool error limit"
        elif (
            state.get("duplicate_action_count", 0)
            >= graph_config.no_progress_limit
            or (
                state.get("no_progress_count", 0)
                >= graph_config.no_progress_limit
                and not _has_unexplored_evidence_tools(state)
            )
        ):
            reason = "no-progress limit"
        elif (
            state.get("tool_call_count", 0)
            >= graph_config.max_tool_calls
        ):
            reason = "tool-call limit"
        else:
            reason = "iteration limit"
        raise ReActLimitReachedError(
            f"ReAct investigation reached the {reason} "
            "without sufficient grounded evidence"
        )

    async def generate_assessment(
        state: InvestigationState,
    ) -> dict[str, object]:
        try:
            async with asyncio.timeout(remaining_runtime(state)):
                assessment = await analyst.analyze_react(
                    incident=state["incident"],
                    observations=state.get("observations", []),
                    retrieved_sections=state.get(
                        "retrieved_sections",
                        [],
                    ),
                    validation_feedback=state.get(
                        "validation_error"
                    ),
                )
        except TimeoutError as exc:
            raise ReActLimitReachedError(
                "ReAct investigation reached the runtime limit"
            ) from exc
        except ValidationError as exc:
            return {
                "assessment_validated": False,
                "assessment_generation_failed": True,
                "validation_error": (
                    "Generated assessment failed schema "
                    f"validation: {exc}"
                ),
                "assessment_repair_count": (
                    state.get("assessment_repair_count", 0) + 1
                ),
            }
        return {
            "assessment": assessment,
            "assessment_generation_failed": False,
            "validation_error": None,
        }

    def route_generation(state: InvestigationState) -> str:
        if not state.get("assessment_generation_failed"):
            return "validate_assessment"
        if (
            state.get("assessment_repair_count", 0)
            <= graph_config.max_repair_attempts
        ):
            return "generate_assessment"
        return "validation_failed"

    def validate_assessment(
        state: InvestigationState,
    ) -> dict[str, object]:
        incident = state["incident"]
        assessment = state["assessment"]
        errors = []
        if assessment.incident_id != incident.incident_id:
            errors.append(
                "Assessment incident ID does not match the "
                "investigated incident"
            )
        retrieved_citations = {
            result.section.citation_id
            for result in state.get("retrieved_sections", [])
        }
        unsupported = sorted(
            set(assessment.citation_ids)
            - retrieved_citations
        )
        if unsupported:
            errors.append(
                "Assessment contains citations that were not "
                "retrieved: " + ", ".join(unsupported)
            )
        if errors:
            return {
                "assessment_validated": False,
                "validation_error": "; ".join(errors),
                "assessment_repair_count": (
                    state.get("assessment_repair_count", 0) + 1
                ),
            }
        return {
            "assessment_validated": True,
            "validation_error": None,
        }

    def route_validation(state: InvestigationState) -> str:
        if state.get("assessment_validated") is True:
            return "complete"
        if (
            state.get("assessment_repair_count", 0)
            <= graph_config.max_repair_attempts
        ):
            return "generate_assessment"
        return "validation_failed"

    def validation_failed(
        state: InvestigationState,
    ) -> dict[str, object]:
        raise ReActAssessmentValidationError(
            state.get("validation_error")
            or "Assessment validation failed"
        )

    graph = StateGraph(InvestigationState)
    graph.add_node("initialize_react", initialize)
    graph.add_node("choose_action", choose_action)
    graph.add_node("execute_tool", execute_tool)
    graph.add_node("prepare_finalize", prepare_finalize)
    graph.add_node(
        "request_additional_evidence",
        request_additional_evidence,
    )
    graph.add_node("stop_for_limit", stop_for_limit)
    graph.add_node(
        "prepare_limit_finalize",
        prepare_limit_finalize,
    )
    graph.add_node(
        "generate_react_assessment",
        generate_assessment,
    )
    graph.add_node(
        "validate_react_assessment",
        validate_assessment,
    )
    graph.add_node("validation_failed", validation_failed)

    graph.add_edge(START, "initialize_react")
    graph.add_edge("initialize_react", "choose_action")
    graph.add_conditional_edges(
        "choose_action",
        route_action,
        {
            "execute_tool": "execute_tool",
            "finalize": "prepare_finalize",
            "request_additional_evidence": (
                "request_additional_evidence"
            ),
        },
    )
    progress_routes = {
        "choose_action": "choose_action",
        "generate_assessment": "generate_react_assessment",
        "prepare_limit_finalize": "prepare_limit_finalize",
        "stop_runtime_limit": "stop_for_limit",
        "stop_tool_error_limit": "stop_for_limit",
        "stop_no_progress": "stop_for_limit",
        "stop_max_tool_calls": "stop_for_limit",
        "stop_max_iterations": "stop_for_limit",
    }
    graph.add_conditional_edges(
        "execute_tool",
        route_after_progress,
        progress_routes,
    )
    graph.add_conditional_edges(
        "prepare_finalize",
        route_after_progress,
        progress_routes,
    )
    graph.add_edge(
        "prepare_limit_finalize",
        "generate_react_assessment",
    )
    graph.add_conditional_edges(
        "generate_react_assessment",
        route_generation,
        {
            "validate_assessment": (
                "validate_react_assessment"
            ),
            "generate_assessment": (
                "generate_react_assessment"
            ),
            "validation_failed": "validation_failed",
        },
    )
    graph.add_conditional_edges(
        "validate_react_assessment",
        route_validation,
        {
            "complete": END,
            "generate_assessment": (
                "generate_react_assessment"
            ),
            "validation_failed": "validation_failed",
        },
    )

    return graph.compile(name="rootpilot_react_investigation")
