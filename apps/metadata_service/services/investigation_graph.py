from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)
from apps.metadata_service.schemas.investigation import (
    InvestigationState,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.analyst import (
    IncidentAnalyst,
)
from apps.metadata_service.services.retriever import (
    RunbookRetriever,
)


def build_investigation_graph(
    retriever: RunbookRetriever,
    analyst: IncidentAnalyst,
    retrieval_limit: int = 3,
) -> CompiledStateGraph:
    if retrieval_limit < 1:
        raise ValueError(
            "Retrieval limit must be at least 1"
        )

    async def retrieve_runbook_context(
        state: InvestigationState,
    ) -> dict[
        str,
        list[RetrievedRunbookSection],
    ]:
        retrieved_sections = await retriever.retrieve(
            incident=state["incident"],
            limit=retrieval_limit,
        )

        return {
            "retrieved_sections": retrieved_sections,
        }

    async def generate_incident_assessment(
        state: InvestigationState,
    ) -> dict[str, IncidentAssessment]:
        assessment = await analyst.analyze(
            incident=state["incident"],
            retrieved_sections=(
                state["retrieved_sections"]
            ),
        )

        return {
            "assessment": assessment,
        }

    def validate_incident_assessment(
        state: InvestigationState,
    ) -> dict[str, bool]:
        incident = state["incident"]
        assessment = state["assessment"]
        retrieved_sections = state[
            "retrieved_sections"
        ]

        if assessment.incident_id != incident.incident_id:
            raise ValueError(
                "Assessment incident ID does not match "
                "the investigated incident"
            )

        retrieved_citation_ids = {
            result.section.citation_id
            for result in retrieved_sections
        }

        unsupported_citation_ids = sorted(
            set(assessment.citation_ids)
            - retrieved_citation_ids
        )

        if unsupported_citation_ids:
            unsupported_citations = ", ".join(
                unsupported_citation_ids
            )

            raise ValueError(
                "Assessment contains citations that were "
                "not retrieved: "
                f"{unsupported_citations}"
            )

        return {
            "assessment_validated": True,
        }

    graph_builder = StateGraph(InvestigationState)

    graph_builder.add_node(
        "retrieve_runbook_context",
        retrieve_runbook_context,
    )
    graph_builder.add_node(
        "generate_incident_assessment",
        generate_incident_assessment,
    )
    graph_builder.add_node(
        "validate_incident_assessment",
        validate_incident_assessment,
    )

    graph_builder.add_edge(
        START,
        "retrieve_runbook_context",
    )
    graph_builder.add_edge(
        "retrieve_runbook_context",
        "generate_incident_assessment",
    )
    graph_builder.add_edge(
        "generate_incident_assessment",
        "validate_incident_assessment",
    )
    graph_builder.add_edge(
        "validate_incident_assessment",
        END,
    )

    return graph_builder.compile()