import json
from pathlib import Path

from apps.metadata_service.schemas.incident import IncidentEvidence


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INCIDENT_DIRECTORY = PROJECT_ROOT / "data" / "incidents"


def load_incident(path: Path) -> IncidentEvidence:
    path = Path(path)

    try:
        raw_incident = json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Incident file contains invalid JSON: {path}"
        ) from exc

    return IncidentEvidence.model_validate(raw_incident)


def load_incidents(
    directory: Path = DEFAULT_INCIDENT_DIRECTORY,
) -> dict[str, IncidentEvidence]:
    directory = Path(directory)
    incident_paths = sorted(directory.glob("*.json"))

    if not incident_paths:
        raise FileNotFoundError(
            f"No incident JSON files found in: {directory}"
        )

    incidents: dict[str, IncidentEvidence] = {}

    for incident_path in incident_paths:
        incident = load_incident(incident_path)

        if incident.incident_id in incidents:
            raise ValueError(
                f"Duplicate incident ID: {incident.incident_id}"
            )

        incidents[incident.incident_id] = incident

    return incidents