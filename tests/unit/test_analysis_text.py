from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.services.analysis_text import (
    build_incident_analysis_text,
)
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.runbook_loader import (
    load_runbooks,
)


def test_build_incident_analysis_text_includes_context() -> None:
    incident = load_incidents()["INC-DB-001"]

    section = next(
        section
        for section in load_runbooks()
        if section.citation_id == "RB-DB-001#diagnosis"
    )

    analysis_text = build_incident_analysis_text(
        incident=incident,
        retrieved_sections=[
            RetrievedRunbookSection(
                section=section,
                score=0.91,
            )
        ],
    )

    assert '"incident_id": "INC-DB-001"' in analysis_text
    assert "INC-DB-001" in analysis_text
    assert "RB-DB-001#diagnosis" in analysis_text
    assert "Similarity score: 0.9100" in analysis_text
    assert "database health check succeeds" in analysis_text