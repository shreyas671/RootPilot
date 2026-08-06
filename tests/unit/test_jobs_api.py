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
        self.committed = False
        self.job_to_return: Job | None = None

    def add(self, job: Job) -> None:
        self.added_job = job

    async def get(
        self,
        model: type[Job],
        job_id: UUID,
    ) -> Job | None:
        assert model is Job

        if self.job_to_return is None:
            return None

        if self.job_to_return.id != job_id:
            return None

        return self.job_to_return

    async def flush(self) -> None:
        assert self.added_job is not None

        now = datetime.now(UTC)

        self.added_job.id = uuid4()
        self.added_job.status = JobStatus.PENDING
        self.added_job.created_at = now
        self.added_job.updated_at = now

    async def refresh(self, job: Job) -> None:
        assert job is self.added_job

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.committed = False


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