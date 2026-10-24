import asyncio
from types import SimpleNamespace

import pytest

import apps.metadata_service.main as main_module


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_lifespan_starts_and_stops_embedded_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_supervisor() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(embedded_worker_enabled=True),
    )
    monkeypatch.setattr(
        main_module,
        "supervise_embedded_worker",
        fake_supervisor,
    )

    async with main_module.lifespan(main_module.app):
        await started.wait()

    assert cancelled.is_set()


@pytest.mark.anyio
async def test_lifespan_skips_disabled_embedded_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def fake_supervisor() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(embedded_worker_enabled=False),
    )
    monkeypatch.setattr(
        main_module,
        "supervise_embedded_worker",
        fake_supervisor,
    )

    async with main_module.lifespan(main_module.app):
        await asyncio.sleep(0)

    assert called is False
