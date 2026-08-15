from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.retrieval_text import (
    build_incident_query,
    build_runbook_search_text,
)
from apps.metadata_service.services.runbook_loader import (
    load_runbooks,
)


def test_build_incident_query_includes_evidence() -> None:
    incident = load_incidents()["INC-DB-001"]

    query = build_incident_query(incident)

    assert "Incident: Checkout API returning" in query
    assert "Service: checkout-api" in query
    assert "db_pool_active_connections: 20 connections" in (
        query
    )
    assert "unable to acquire database connection" in query
    assert "transaction handling" in query


def test_build_runbook_search_text_includes_context() -> None:
    section = next(
        section
        for section in load_runbooks()
        if section.citation_id == "RB-DB-001#diagnosis"
    )

    search_text = build_runbook_search_text(section)

    assert (
        "Runbook: Database Connection-Pool Exhaustion"
        in search_text
    )
    assert "Section: Diagnosis" in search_text
    assert "database health check succeeds" in search_text