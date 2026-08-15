from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.runbook import (
    RunbookSection,
)


def build_incident_query(
    incident: IncidentEvidence,
) -> str:
    lines = [
        f"Incident: {incident.title}",
        f"Service: {incident.service}",
        f"Summary: {incident.summary}",
        "",
        "Symptoms:",
    ]

    lines.extend(
        f"- {symptom}"
        for symptom in incident.symptoms
    )

    lines.extend(
        [
            "",
            "Metrics:",
        ]
    )

    lines.extend(
        (
            f"- {metric.name}: "
            f"{metric.value:g} {metric.unit}"
        )
        for metric in incident.metrics
    )

    lines.extend(
        [
            "",
            "Logs:",
        ]
    )

    lines.extend(
        f"- {log.level}: {log.message}"
        for log in incident.logs
    )

    if incident.recent_changes:
        lines.extend(
            [
                "",
                "Recent changes:",
            ]
        )

        lines.extend(
            f"- {change.description}"
            for change in incident.recent_changes
        )

    return "\n".join(lines)


def build_runbook_search_text(
    section: RunbookSection,
) -> str:
    return "\n".join(
        [
            f"Runbook: {section.runbook_title}",
            f"Section: {section.section_title}",
            "",
            section.content,
        ]
    )