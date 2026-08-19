from fastapi.testclient import TestClient

from apps.metadata_service.main import app


def test_list_incidents_returns_catalog() -> None:
    with TestClient(app) as client:
        response = client.get("/incidents")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    assert {item["incident_id"] for item in body} == {
        "INC-CACHE-001",
        "INC-DB-001",
        "INC-KAFKA-001",
        "INC-MEMORY-001",
        "INC-TLS-001",
    }
    assert all(item["input_path"] for item in body)
