from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from apps.metadata_service.schemas.investigation import (
    InvestigationState,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.retriever import (
    RunbookRetriever,
)


def build_investigation_graph(
    retriever: RunbookRetriever,
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

    graph_builder = StateGraph(InvestigationState)

    graph_builder.add_node(
        "retrieve_runbook_context",
        retrieve_runbook_context,
    )

    graph_builder.add_edge(
        START,
        "retrieve_runbook_context",
    )
    graph_builder.add_edge(
        "retrieve_runbook_context",
        END,
    )

    return graph_builder.compile()