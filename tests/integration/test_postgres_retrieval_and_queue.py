import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete

from apps.metadata_service.database import get_engine, get_session_factory
from apps.metadata_service.models.job import Job, JobStatus
from apps.metadata_service.models.runbook_embedding import (
    EMBEDDING_DIMENSIONS,
    RunbookEmbedding,
)
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.job_queue import (
    claim_next_investigation_job,
    renew_investigation_job_lease,
    requeue_investigation_job,
)
from apps.metadata_service.services.postgres_retriever import (
    PostgresRunbookRetriever,
)
from apps.metadata_service.services.runbook_loader import (
    load_runbooks,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
        reason=(
            "set RUN_POSTGRES_INTEGRATION=1 to run "
            "PostgreSQL integration tests"
        ),
    ),
]


class DeterministicEmbeddingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        self.calls += 1
        vectors = []

        for text in texts:
            normalized = text.lower()
            vector = [0.0] * EMBEDDING_DIMENSIONS

            if "database" in normalized or "postgres" in normalized:
                vector[0] = 1.0
            else:
                vector[1] = 1.0

            vectors.append(vector)

        return vectors


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
async def isolate_async_connection_pool() -> object:
    await get_engine().dispose()
    yield
    await get_engine().dispose()


@pytest.mark.anyio
async def test_pgvector_index_is_idempotent_and_retrieves() -> None:
    session_factory = get_session_factory()
    provider = DeterministicEmbeddingProvider()

    async with session_factory() as session:
        await session.execute(delete(RunbookEmbedding))
        await session.commit()

    try:
        retriever = await PostgresRunbookRetriever.create(
            embedding_provider=provider,
            session_factory=session_factory,
            embedding_model="deterministic-v1",
            sections=load_runbooks(),
        )
        indexing_calls = provider.calls

        changed = await retriever.index_sections(
            load_runbooks()
        )
        results = await retriever.retrieve(
            incident=load_incidents()["INC-DB-001"],
            limit=2,
        )

        assert changed == 0
        assert provider.calls == indexing_calls + 1
        assert results
        assert results[0].section.runbook_id == "RB-DB-001"
        assert results[0].score == pytest.approx(1.0)
    finally:
        async with session_factory() as session:
            await session.execute(delete(RunbookEmbedding))
            await session.commit()


@pytest.mark.anyio
async def test_queue_claim_renew_retry_and_exhaustion() -> None:
    session_factory = get_session_factory()
    job = Job(
        id=uuid4(),
        input_path="data/incidents/INC-DB-001.json",
        incident_id="INC-DB-001",
        status=JobStatus.PENDING,
        max_attempts=2,
    )
    exhausted_job = Job(
        id=uuid4(),
        input_path="data/incidents/INC-KAFKA-001.json",
        incident_id="INC-KAFKA-001",
        status=JobStatus.PROCESSING,
        attempt_count=1,
        max_attempts=1,
        claimed_by="dead-worker",
        lease_expires_at=(
            datetime.now(UTC) - timedelta(minutes=1)
        ),
    )

    async with session_factory() as session:
        session.add_all([job, exhausted_job])
        await session.commit()

    try:
        async with session_factory() as session:
            claimed = await claim_next_investigation_job(
                session=session,
                worker_id="worker-1",
                lease_seconds=30,
                target_job_id=job.id,
            )

        assert claimed is not None
        assert claimed.id == job.id
        assert claimed.status is JobStatus.PROCESSING
        assert claimed.attempt_count == 1
        assert claimed.claimed_by == "worker-1"

        first_lease = claimed.lease_expires_at

        async with session_factory() as session:
            renewed = await renew_investigation_job_lease(
                session=session,
                job_id=job.id,
                worker_id="worker-1",
                lease_seconds=60,
            )

        assert renewed.lease_expires_at > first_lease

        async with session_factory() as session:
            requeued = await requeue_investigation_job(
                session=session,
                job_id=job.id,
                error_message="temporary outage",
                retry_delay_seconds=0,
            )

        assert requeued.status is JobStatus.PENDING
        assert requeued.claimed_by is None

        async with session_factory() as session:
            claimed_again = await claim_next_investigation_job(
                session=session,
                worker_id="worker-2",
                lease_seconds=30,
                target_job_id=job.id,
            )

        assert claimed_again is not None
        assert claimed_again.id == job.id
        assert claimed_again.attempt_count == 2

        async with session_factory() as session:
            terminal = await requeue_investigation_job(
                session=session,
                job_id=job.id,
                error_message="still unavailable",
                retry_delay_seconds=0,
            )

        assert terminal.status is JobStatus.FAILED

        async with session_factory() as session:
            no_job = await claim_next_investigation_job(
                session=session,
                worker_id="worker-3",
                lease_seconds=30,
                target_job_id=exhausted_job.id,
            )
            cleaned_up = await session.get(Job, exhausted_job.id)

        assert no_job is None
        assert cleaned_up is not None
        assert cleaned_up.status is JobStatus.FAILED
        assert cleaned_up.claimed_by is None
    finally:
        async with session_factory() as session:
            await session.execute(
                delete(Job).where(
                    Job.id.in_([job.id, exhausted_job.id])
                )
            )
            await session.commit()
