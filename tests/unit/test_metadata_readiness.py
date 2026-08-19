from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.metadata_service.database import get_db_session
from apps.metadata_service.main import app

client = TestClient(app)


def test_readiness_when_database_is_available() -> None:
    session = AsyncMock(spec=AsyncSession)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "metadata-service",
        "database": "connected",
    }
    session.execute.assert_awaited_once()


def test_readiness_when_database_is_unavailable() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = SQLAlchemyError("Connection failed")

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Database unavailable",
    }
    session.execute.assert_awaited_once()