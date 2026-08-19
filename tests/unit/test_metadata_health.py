from fastapi.testclient import TestClient

from apps.metadata_service.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "metadata-service",
    }
    assert response.headers["x-content-type-options"] == (
        "nosniff"
    )
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"]


def test_prometheus_metrics() -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "rootpilot_http_requests_total" in response.text
