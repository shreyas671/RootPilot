import argparse
import asyncio
import logging
import os
import socket
from collections.abc import Awaitable
from contextlib import suppress
from uuid import UUID

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from apps.metadata_service.config import get_settings
from apps.metadata_service.database import get_session_factory
from apps.metadata_service.models.job import JobStatus
from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.investigation_execution import (
    SessionFactory,
    execute_claimed_and_persist_investigation,
)
from apps.metadata_service.services.investigation_graph import (
    build_investigation_graph,
)
from apps.metadata_service.services.investigation_reports import (
    mark_investigation_job_failed,
)
from apps.metadata_service.services.job_queue import (
    claim_next_investigation_job,
    renew_investigation_job_lease,
    requeue_investigation_job,
)
from apps.metadata_service.services.openai_analyst import (
    INCIDENT_ANALYST_PROMPT_VERSION,
    OpenAIIncidentAnalyst,
)
from apps.metadata_service.services.openai_client import (
    create_openai_client,
)
from apps.metadata_service.services.openai_embedding import (
    OpenAIEmbeddingProvider,
)
from apps.metadata_service.services.retriever_factory import (
    create_runbook_retriever,
)
from apps.metadata_service.services.runbook_loader import (
    load_runbooks,
)

TRANSIENT_OPENAI_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
def default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Process queued RootPilot investigations"
        )
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Process at most one available job and exit"
        ),
    )
    parser.add_argument(
        "--worker-id",
        default=default_worker_id(),
        help="Stable identity recorded on claimed jobs",
    )

    return parser.parse_args()


def format_error(exc: Exception) -> str:
    detail = str(exc).strip()
    message = exc.__class__.__name__

    if detail:
        message = f"{message}: {detail}"

    return message


async def run_with_lease_heartbeat[ResultT](
    operation: Awaitable[ResultT],
    job_id: UUID,
    worker_id: str,
    lease_seconds: int,
    session_factory: SessionFactory,
) -> ResultT:
    async def heartbeat() -> None:
        interval = max(0.2, lease_seconds / 3)

        while True:
            await asyncio.sleep(interval)

            async with session_factory() as session:
                await renew_investigation_job_lease(
                    session=session,
                    job_id=job_id,
                    worker_id=worker_id,
                    lease_seconds=lease_seconds,
                )

    operation_task = asyncio.create_task(operation)
    heartbeat_task = asyncio.create_task(heartbeat())
    done, _ = await asyncio.wait(
        {operation_task, heartbeat_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if operation_task in done:
        heartbeat_task.cancel()

        with suppress(asyncio.CancelledError):
            await heartbeat_task

        return await operation_task

    operation_task.cancel()

    with suppress(asyncio.CancelledError):
        await operation_task

    await heartbeat_task
    raise RuntimeError("Worker heartbeat stopped unexpectedly")


async def run_worker(
    worker_id: str,
    once: bool = False,
) -> None:
    settings = get_settings()
    session_factory = get_session_factory()
    incidents = load_incidents()
    client = create_openai_client(settings)
    logger = logging.getLogger("rootpilot.worker")

    try:
        embedding_provider = OpenAIEmbeddingProvider(
            client=client,
            model=settings.openai_embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        retriever = await create_runbook_retriever(
            settings=settings,
            embedding_provider=embedding_provider,
            sections=load_runbooks(),
        )
        analyst = OpenAIIncidentAnalyst(
            client=client,
            model=settings.openai_analysis_model,
        )
        workflow = build_investigation_graph(
            retriever=retriever,
            analyst=analyst,
            retrieval_limit=(
                settings.default_retrieval_limit
            ),
            minimum_relevance_score=(
                settings.default_minimum_relevance_score
            ),
        )

        while True:
            async with session_factory() as session:
                job = await claim_next_investigation_job(
                    session=session,
                    worker_id=worker_id,
                    lease_seconds=(
                        settings.worker_lease_seconds
                    ),
                )

            if job is None:
                if once:
                    return

                await asyncio.sleep(
                    settings.worker_poll_interval_seconds
                )
                continue

            incident = incidents.get(job.incident_id or "")

            if incident is None:
                async with session_factory() as session:
                    await mark_investigation_job_failed(
                        session=session,
                        job_id=job.id,
                        error_message=(
                            "Job does not reference a known "
                            "incident_id"
                        ),
                    )

                if once:
                    return

                continue

            logger.info(
                "investigation_started",
                extra={
                    "job_id": job.id,
                    "incident_id": incident.incident_id,
                },
            )

            try:
                report = await run_with_lease_heartbeat(
                    execute_claimed_and_persist_investigation(
                        job_id=job.id,
                        incident=incident,
                        workflow=workflow,
                        session_factory=session_factory,
                        embedding_model=(
                            settings.openai_embedding_model
                        ),
                        analysis_model=(
                            settings.openai_analysis_model
                        ),
                        prompt_version=(
                            INCIDENT_ANALYST_PROMPT_VERSION
                        ),
                        retrieval_backend=(
                            settings.retrieval_backend
                        ),
                        retrieval_limit=(
                            settings.default_retrieval_limit
                        ),
                        minimum_relevance_score=(
                            settings.default_minimum_relevance_score
                        ),
                        mark_failure=False,
                    ),
                    job_id=job.id,
                    worker_id=worker_id,
                    lease_seconds=(
                        settings.worker_lease_seconds
                    ),
                    session_factory=session_factory,
                )
            except TRANSIENT_OPENAI_ERRORS as exc:
                retry_delay = min(
                    60.0,
                    float(2**job.attempt_count),
                )

                async with session_factory() as session:
                    retried_job = (
                        await requeue_investigation_job(
                            session=session,
                            job_id=job.id,
                            error_message=format_error(exc),
                            retry_delay_seconds=retry_delay,
                        )
                    )

                logger.warning(
                    "investigation_transient_failure",
                    extra={
                        "job_id": job.id,
                        "incident_id": incident.incident_id,
                        "status_code": (
                            retried_job.status.value
                        ),
                    },
                )
            except Exception as exc:
                async with session_factory() as session:
                    await mark_investigation_job_failed(
                        session=session,
                        job_id=job.id,
                        error_message=format_error(exc),
                    )

                logger.exception(
                    "investigation_failed",
                    extra={
                        "job_id": job.id,
                        "incident_id": incident.incident_id,
                    },
                )
            else:
                logger.info(
                    "investigation_completed",
                    extra={
                        "job_id": job.id,
                        "incident_id": incident.incident_id,
                        "status_code": JobStatus.COMPLETED.value,
                    },
                )

                if report.id is None:
                    raise RuntimeError(
                        "Persisted report has no identifier"
                    )

            if once:
                return
    finally:
        await client.close()


def main() -> None:
    arguments = parse_arguments()

    try:
        asyncio.run(
            run_worker(
                worker_id=arguments.worker_id,
                once=arguments.once,
            )
        )
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
