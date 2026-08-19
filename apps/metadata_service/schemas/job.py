from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from apps.metadata_service.models.job import JobStatus

ErrorMessage = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=4000,
    ),
]


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(
        pattern=r"^INC-[A-Z]+-\d{3}$",
    )
    max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
    )


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
    incident_id: str | None = None
    status: JobStatus
    error_message: str | None
    attempt_count: int = 0
    max_attempts: int = 3
    claimed_by: str | None = None
    lease_expires_at: datetime | None = None
    scheduled_at: datetime | None = None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
