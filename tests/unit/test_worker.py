import asyncio
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Self
from uuid import uuid4

import pytest

import apps.metadata_service.commands.run_worker as worker_module
from apps.metadata_service.commands.run_worker import (
    run_with_lease_heartbeat,
)


class FakeSession:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def session_factory() -> AbstractAsyncContextManager[object]:
    return FakeSession()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_lease_heartbeat_renews_long_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renewals: list[object] = []

    async def fake_renew(**kwargs: object) -> None:
        renewals.append(kwargs)

    async def operation() -> str:
        await asyncio.sleep(0.35)
        return "complete"

    monkeypatch.setattr(
        worker_module,
        "renew_investigation_job_lease",
        fake_renew,
    )

    result = await run_with_lease_heartbeat(
        operation=operation(),
        job_id=uuid4(),
        worker_id="worker-1",
        lease_seconds=1,
        session_factory=session_factory,
    )

    assert result == "complete"
    assert len(renewals) == 1


@pytest.mark.anyio
async def test_lease_failure_cancels_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancelled = False

    async def fake_renew(**kwargs: object) -> None:
        raise RuntimeError("database unavailable")

    async def operation() -> None:
        nonlocal cancelled

        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled = True
            raise

    monkeypatch.setattr(
        worker_module,
        "renew_investigation_job_lease",
        fake_renew,
    )

    with pytest.raises(
        RuntimeError,
        match="database unavailable",
    ):
        await run_with_lease_heartbeat(
            operation=operation(),
            job_id=uuid4(),
            worker_id="worker-1",
            lease_seconds=1,
            session_factory=session_factory,
        )

    assert cancelled is True
