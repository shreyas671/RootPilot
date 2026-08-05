from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from apps.metadata_service.models.job import JobStatus


InputPath = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=1024,
    ),
]


class JobCreate(BaseModel):
    input_path: InputPath


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    input_path: str
    status: JobStatus
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime