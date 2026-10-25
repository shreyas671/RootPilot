from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from apps.metadata_service import observability
from apps.metadata_service.config import Settings
from apps.metadata_service.observability import (
    configure_langsmith_tracing,
    flush_langsmith_traces,
)
from apps.metadata_service.services.investigation_execution import (
    _trace_investigation_inputs,
)
from apps.metadata_service.services.openai_embedding import (
    _trace_embedding_inputs,
    _trace_embedding_outputs,
)


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "postgres_user": "rootpilot",
        "postgres_password": "database-password",
        "postgres_db": "rootpilot",
        "postgres_host": "localhost",
        "postgres_port": 5432,
        "openai_api_key": "model-gateway-test-key",
        "langsmith_tracing": False,
        "langsmith_api_key": None,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_langsmith_tracing_requires_api_key() -> None:
    with pytest.raises(
        ValidationError,
        match=(
            "LANGSMITH_API_KEY is required when "
            "LANGSMITH_TRACING is enabled"
        ),
    ):
        make_settings(langsmith_tracing=True)


def test_configure_langsmith_tracing_exports_settings(
    monkeypatch,
) -> None:
    environment: dict[str, str] = {}
    monkeypatch.setattr(
        observability,
        "os",
        SimpleNamespace(environ=environment),
    )

    settings = make_settings(
        langsmith_tracing=True,
        langsmith_api_key="langsmith-test-key",
        langsmith_project="rootpilot-test",
        langsmith_endpoint=(
            "https://langsmith.example.test"
        ),
        langsmith_workspace_id="workspace-test",
        langsmith_hide_inputs=True,
        langsmith_hide_outputs=False,
    )

    configure_langsmith_tracing(settings)

    assert environment["LANGSMITH_TRACING"] == "true"
    assert environment["LANGSMITH_API_KEY"] == (
        "langsmith-test-key"
    )
    assert environment["LANGSMITH_PROJECT"] == (
        "rootpilot-test"
    )
    assert environment["LANGSMITH_ENDPOINT"] == (
        "https://langsmith.example.test"
    )
    assert environment["LANGSMITH_WORKSPACE_ID"] == (
        "workspace-test"
    )
    assert environment["LANGSMITH_HIDE_INPUTS"] == (
        "true"
    )
    assert environment["LANGSMITH_HIDE_OUTPUTS"] == (
        "false"
    )


def test_disabled_langsmith_does_not_flush(monkeypatch) -> None:
    flushed = False

    def fake_get_cached_client() -> object:
        nonlocal flushed
        flushed = True
        return object()

    monkeypatch.setattr(
        "apps.metadata_service.observability."
        "run_trees.get_cached_client",
        fake_get_cached_client,
    )

    flush_langsmith_traces(make_settings())

    assert flushed is False


def test_embedding_trace_records_shape_not_content() -> None:
    inputs = _trace_embedding_inputs(
        {
            "self": SimpleNamespace(
                _model="embedding-model-test"
            ),
            "texts": [
                "sensitive incident evidence",
                "private runbook content",
            ],
        }
    )
    outputs = _trace_embedding_outputs(
        [[0.1, 0.2], [0.3, 0.4]]
    )

    assert inputs == {
        "model": "embedding-model-test",
        "text_count": 2,
        "character_count": 50,
    }
    assert "sensitive" not in str(inputs)
    assert "private" not in str(inputs)
    assert outputs == {
        "vector_count": 2,
        "dimensions": 2,
    }


def test_investigation_trace_omits_incident_payload() -> None:
    inputs = _trace_investigation_inputs(
        {
            "job_id": "job-test",
            "incident": SimpleNamespace(
                incident_id="INC-TEST-001",
                summary="sensitive incident summary",
            ),
            "embedding_model": "embedding-model-test",
            "analysis_model": "analysis-model-test",
            "retrieval_backend": "postgres",
            "retrieval_limit": 3,
            "minimum_relevance_score": 0.25,
        }
    )

    assert inputs["job_id"] == "job-test"
    assert inputs["incident_id"] == "INC-TEST-001"
    assert "sensitive incident summary" not in str(inputs)
