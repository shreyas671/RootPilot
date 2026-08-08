from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from apps.metadata_service.models.job import JobStatus
from apps.metadata_service.schemas.job import (
    JobCreate,
    JobResponse,
    JobStatusUpdate,
)


def test_job_create_accepts_valid_input_path() -> None:
    request = JobCreate(input_path="/videos/demo.mp4")

    assert request.input_path == "/videos/demo.mp4"


def test_job_create_removes_surrounding_whitespace() -> None:
    request = JobCreate(input_path="  /videos/demo.mp4  ")

    assert request.input_path == "/videos/demo.mp4"


@pytest.mark.parametrize(
    "input_path",
    [
        "",
        "   ",
        "x" * 1025,
    ],
)
def test_job_create_rejects_invalid_input_path(input_path: str) -> None:
    with pytest.raises(ValidationError):
        JobCreate(input_path=input_path)


def test_job_response_reads_job_attributes() -> None:
    now = datetime.now(UTC)
    job_id = uuid4()

    job = SimpleNamespace(
        id=job_id,
        input_path="/videos/demo.mp4",
        status=JobStatus.PENDING,
        error_message=None,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )

    response = JobResponse.model_validate(job)

    assert response.id == job_id
    assert response.input_path == "/videos/demo.mp4"
    assert response.status == JobStatus.PENDING
    assert response.created_at == now


def test_job_status_update_accepts_failed_with_error_message() -> None:
    request = JobStatusUpdate(
        status=JobStatus.FAILED,
        error_message="  Video decoder unavailable  ",
    )

    assert request.status is JobStatus.FAILED
    assert request.error_message == "Video decoder unavailable"


def test_job_status_update_requires_error_message_for_failed() -> None:
    with pytest.raises(
        ValidationError,
        match="error_message is required",
    ):
        JobStatusUpdate(status=JobStatus.FAILED)


@pytest.mark.parametrize(
    "job_status",
    [
        JobStatus.PENDING,
        JobStatus.PROCESSING,
        JobStatus.COMPLETED,
    ],
)
def test_job_status_update_rejects_error_for_non_failed_status(
    job_status: JobStatus,
) -> None:
    with pytest.raises(
        ValidationError,
        match="error_message is only allowed",
    ):
        JobStatusUpdate(
            status=job_status,
            error_message="Unexpected error",
        )


def test_job_status_update_rejects_blank_error_message() -> None:
    with pytest.raises(ValidationError):
        JobStatusUpdate(
            status=JobStatus.FAILED,
            error_message="   ",
        )