from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from apps.metadata_service.database import get_db_session
from apps.metadata_service.main import app
from apps.metadata_service.models.job import Job, JobStatus


class FakeSession:
    def __init__(self) -> None:
        self.added_job: Job | None = None
        self.job_to_return: Job | None = None
        self.committed = False
        self.rolled_back = False
        self.used_row_lock = False

    def add(self, job: Job) -> None:
        self.added_job = job

    async def get(
        self,
        model: type[Job],
        job_id: UUID,
        *,
        with_for_update: bool = False,
    ) -> Job | None:
        assert model is Job

        self.used_row_lock = with_for_update

        if self.job_to_return is None:
            return None

        if self.job_to_return.id != job_id:
            return None

        return self.job_to_return

    async def flush(self) -> None:
        now = datetime.now(UTC)

        if self.added_job is not None:
            self.added_job.id = uuid4()
            self.added_job.status = JobStatus.PENDING
            self.added_job.created_at = now
            self.added_job.updated_at = now

        if self.job_to_return is not None:
            self.job_to_return.updated_at = now

    async def refresh(self, job: Job) -> None:
        assert (
            job is self.added_job
            or job is self.job_to_return
        )

    async def commit(self) -> None:
        self.committed = True
        self.rolled_back = False

    async def rollback(self) -> None:
        self.committed = False
        self.rolled_back = True

@pytest.fixture
def client_and_session() -> Iterator[tuple[TestClient, FakeSession]]:
    fake_session = FakeSession()

    async def override_get_db_session() -> AsyncIterator[FakeSession]:
        yield fake_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        with TestClient(app) as client:
            yield client, fake_session
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def make_job(
    job_status: JobStatus,
    *,
    started_at: datetime | None = None,
) -> Job:
    now = datetime.now(UTC)

    return Job(
        id=uuid4(),
        input_path="/videos/demo.mp4",
        status=job_status,
        error_message=None,
        started_at=started_at,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )

def test_create_job_returns_201(
    client_and_session: tuple[TestClient, FakeSession],
) -> None:
    client, fake_session = client_and_session

    response = client.post(
        "/jobs",
        json={"input_path": "  /videos/demo.mp4  "},
    )

    assert response.status_code == 201

    body = response.json()

    assert body["input_path"] == "/videos/demo.mp4"
    assert body["status"] == "pending"
    assert body["error_message"] is None
    assert body["started_at"] is None
    assert body["completed_at"] is None
    assert body["id"] is not None
    assert body["created_at"] is not None
    assert body["updated_at"] is not None

    assert fake_session.added_job is not None
    assert fake_session.committed is True


def test_create_job_rejects_invalid_input_path(
    client_and_session: tuple[TestClient, FakeSession],
) -> None:
    client, fake_session = client_and_session

    response = client.post(
        "/jobs",
        json={"input_path": "   "},
    )

    assert response.status_code == 422
    assert fake_session.added_job is None
    assert fake_session.committed is False


def test_get_job_returns_existing_job(
    client_and_session: tuple[TestClient, FakeSession],
) -> None:
    client, fake_session = client_and_session

    job_id = uuid4()
    now = datetime.now(UTC)

    fake_session.job_to_return = Job(
        id=job_id,
        input_path="/videos/demo.mp4",
        status=JobStatus.PENDING,
        error_message=None,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )

    response = client.get(f"/jobs/{job_id}")

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == str(job_id)
    assert body["input_path"] == "/videos/demo.mp4"
    assert body["status"] == "pending"
    assert body["error_message"] is None
    assert body["started_at"] is None
    assert body["completed_at"] is None


def test_get_job_returns_404_when_job_does_not_exist(
    client_and_session: tuple[TestClient, FakeSession],
) -> None:
    client, _ = client_and_session

    response = client.get(f"/jobs/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}


def test_get_job_rejects_invalid_uuid(
    client_and_session: tuple[TestClient, FakeSession],
) -> None:
    client, _ = client_and_session

    response = client.get("/jobs/not-a-valid-uuid")

    assert response.status_code == 422

def test_update_job_status_from_pending_to_processing(
    client_and_session: tuple[TestClient, FakeSession],
) -> None:
    client, fake_session = client_and_session

    job = make_job(JobStatus.PENDING)
    fake_session.job_to_return = job

    response = client.patch(
        f"/jobs/{job.id}/status",
        json={"status": "processing"},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "processing"
    assert body["started_at"] is not None
    assert body["completed_at"] is None
    assert body["error_message"] is None

    assert job.status is JobStatus.PROCESSING
    assert job.started_at is not None
    assert fake_session.used_row_lock is True
    assert fake_session.committed is True
    assert fake_session.rolled_back is False


def test_update_job_status_from_processing_to_completed(
    client_and_session: tuple[TestClient, FakeSession],
) -> None:
    client, fake_session = client_and_session

    job = make_job(
        JobStatus.PROCESSING,
        started_at=datetime.now(UTC),
    )
    fake_session.job_to_return = job

    response = client.patch(
        f"/jobs/{job.id}/status",
        json={"status": "completed"},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "completed"
    assert body["started_at"] is not None
    assert body["completed_at"] is not None
    assert body["error_message"] is None

    assert job.status is JobStatus.COMPLETED
    assert job.completed_at is not None
    assert fake_session.committed is True


def test_update_job_status_from_processing_to_failed(
    client_and_session: tuple[TestClient, FakeSession],
) -> None:
    client, fake_session = client_and_session

    job = make_job(
        JobStatus.PROCESSING,
        started_at=datetime.now(UTC),
    )
    fake_session.job_to_return = job

    response = client.patch(
        f"/jobs/{job.id}/status",
        json={
            "status": "failed",
            "error_message": "  Video decoder unavailable  ",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "failed"
    assert body["completed_at"] is not None
    assert body["error_message"] == "Video decoder unavailable"

    assert job.status is JobStatus.FAILED
    assert job.error_message == "Video decoder unavailable"
    assert fake_session.committed is True


def test_update_job_status_rejects_invalid_transition(
    client_and_session: tuple[TestClient, FakeSession],
) -> None:
    client, fake_session = client_and_session

    job = make_job(JobStatus.PENDING)
    fake_session.job_to_return = job

    response = client.patch(
        f"/jobs/{job.id}/status",
        json={"status": "completed"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Cannot transition job from pending to completed"
    }

    assert job.status is JobStatus.PENDING
    assert fake_session.used_row_lock is True
    assert fake_session.committed is False
    assert fake_session.rolled_back is True


def test_update_job_status_returns_404_for_missing_job(
    client_and_session: tuple[TestClient, FakeSession],
) -> None:
    client, fake_session = client_and_session

    response = client.patch(
        f"/jobs/{uuid4()}/status",
        json={"status": "processing"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}
    assert fake_session.committed is False


def test_update_job_status_rejects_failed_without_error_message(
    client_and_session: tuple[TestClient, FakeSession],
) -> None:
    client, fake_session = client_and_session

    job = make_job(JobStatus.PROCESSING)
    fake_session.job_to_return = job

    response = client.patch(
        f"/jobs/{job.id}/status",
        json={"status": "failed"},
    )

    assert response.status_code == 422
    assert job.status is JobStatus.PROCESSING
    assert fake_session.committed is False