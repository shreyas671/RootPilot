from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)


def build_incident_analysis_text(
    incident: IncidentEvidence,
    retrieved_sections: list[
        RetrievedRunbookSection
    ],
) -> str:
    if not retrieved_sections:
        raise ValueError(
            "At least one retrieved section is required"
        )

    lines = [
        "Incident evidence (JSON):",
        incident.model_dump_json(indent=2),
        "",
        "Retrieved runbook sections:",
    ]

    for rank, result in enumerate(
        retrieved_sections,
        start=1,
    ):
        section = result.section

        lines.extend(
            [
                "",
                f"[Retrieved section {rank}]",
                f"Citation ID: {section.citation_id}",
                f"Similarity score: {result.score:.4f}",
                f"Runbook: {section.runbook_title}",
                f"Section: {section.section_title}",
                "Content:",
                section.content,
            ]
        )

    return "\n".join(lines)