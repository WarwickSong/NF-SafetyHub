from fastapi.testclient import TestClient

from main import app


def test_live_health_check_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"].startswith("req_")


def test_ready_health_check_returns_status_and_checks():
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ready", "not_ready"}
    assert "database" in payload["checks"]
    assert "rules" in payload["checks"]
