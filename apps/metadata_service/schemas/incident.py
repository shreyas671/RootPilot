from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IncidentMetric(EvidenceModel):
    name: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)


class IncidentLog(EvidenceModel):
    timestamp: datetime
    level: str = Field(min_length=1)
    message: str = Field(min_length=1)


class IncidentChange(EvidenceModel):
    timestamp: datetime
    description: str = Field(min_length=1)


class IncidentEvidence(EvidenceModel):
    incident_id: str = Field(
        min_length=1,
        pattern=r"^INC-[A-Z]+-\d{3}$",
    )
    title: str = Field(min_length=1)
    service: str = Field(min_length=1)
    started_at: datetime
    summary: str = Field(min_length=1)
    symptoms: list[str] = Field(min_length=1)
    metrics: list[IncidentMetric] = Field(min_length=1)
    logs: list[IncidentLog] = Field(min_length=1)
    recent_changes: list[IncidentChange]