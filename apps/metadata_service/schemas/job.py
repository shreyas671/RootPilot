from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    model_validator,
)

from apps.metadata_service.models.job import JobStatus


InputPath = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=1024,
    ),
]

ErrorMessage = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=4000,
    ),
]


class JobCreate(BaseModel):
    input_path: InputPath


class JobStatusUpdate(BaseModel):
    status: JobStatus
    error_message: ErrorMessage | None = None

    @model_validator(mode="after")
    def validate_error_message(self) -> Self:
        if self.status is JobStatus.FAILED and self.error_message is None:
            raise ValueError(
                "error_message is required when status is failed"
            )

        if (
            self.status is not JobStatus.FAILED
            and self.error_message is not None
        ):
            raise ValueError(
                "error_message is only allowed when status is failed"
            )

        return self


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