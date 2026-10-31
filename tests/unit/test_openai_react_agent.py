import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.metadata_service.schemas.react import (
    QueryMetricsAction,
    ReactDecision,
)
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.openai_react_agent import (
    REACT_PLANNER_INSTRUCTIONS,
    OpenAIReActAgent,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_chat_planner_returns_structured_action() -> None:
    expected = ReactDecision(
        hypothesis="The database pool may be exhausted.",
        rationale="Inspect the waiter count.",
        action=QueryMetricsAction(
            tool="query_metrics",
            service="checkout-api",
            metric="db_pool_waiters",
            time_range="30m",
        ),
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=expected.model_dump_json()
                    )
                )
            ]
        )
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)
        )
    )
    agent = OpenAIReActAgent(
        client=client,
        model="analysis-test",
        api="chat_completions",
    )

    decision = await agent.decide(
        incident=load_incidents()["INC-DB-001"],
        steps=[],
        observations=[],
        remaining_iterations=8,
        remaining_tool_calls=10,
    )

    assert decision == expected
    request = create.await_args.kwargs
    assert request["model"] == "analysis-test"
    assert request["response_format"]["type"] == (
        "json_schema"
    )
    assert REACT_PLANNER_INSTRUCTIONS in (
        request["messages"][0]["content"]
    )
    payload = json.loads(request["messages"][1]["content"])
    assert "db_pool_waiters" in payload["incident"][
        "available_metric_names"
    ]
    assert "metrics" not in payload["incident"]
    assert "logs" not in payload["incident"]
    assert "recent_changes" not in payload["incident"]
