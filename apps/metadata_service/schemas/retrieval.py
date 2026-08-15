from pydantic import BaseModel, ConfigDict, Field

from apps.metadata_service.schemas.runbook import (
    RunbookSection,
)


class RetrievedRunbookSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: RunbookSection
    score: float = Field(ge=-1.0, le=1.0)