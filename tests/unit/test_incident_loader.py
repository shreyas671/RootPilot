from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.metadata_service.services.incident_loader import (
    load_incident,
    load_incident_catalog,
    load_incidents,
)


def test_load_incidents_returns_all_fixtures() -> None:
    incidents = load_incidents()

    assert set(incidents) == {
        "INC-CACHE-001",
        "INC-DB-001",
        "INC-KAFKA-001",
        "INC-MEMORY-001",
        "INC-TLS-001",
    }

    assert incidents["INC-DB-001"].service == "checkout-api"
    assert incidents["INC-KAFKA-001"].service == "order-worker"


def test_load_incident_catalog_exposes_queue_inputs() -> None:
    catalog = load_incident_catalog()

    assert len(catalog) == 5
    assert catalog[0].incident_id == "INC-CACHE-001"
    assert catalog[0].input_path == (
        "data/incidents/cache_hot_key.json"
    )


def test_load_incident_parses_nested_evidence() -> None:
    incidents = load_incidents()
    incident = incidents["INC-DB-001"]

    assert incident.started_at.tzinfo is not None
    assert incident.metrics[1].name == "db_pool_active_connections"
    assert incident.metrics[1].value == 20
    assert incident.logs[0].level == "ERROR"
    assert incident.recent_changes[0].timestamp.tzinfo is not None


def test_load_incident_rejects_missing_fields(
    tmp_path: Path,
) -> None:
    invalid_incident = tmp_path / "invalid_incident.json"

    invalid_incident.write_text(
        '{"incident_id": "INC-TEST-001"}',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_incident(invalid_incident)
