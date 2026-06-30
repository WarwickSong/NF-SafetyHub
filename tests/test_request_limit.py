from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from middleware.request_limit import RequestBodyLimitMiddleware


def test_request_body_limit_middleware_rejects_large_content_length(monkeypatch):
    monkeypatch.setattr("middleware.request_limit.settings.request_max_body_mb", 1)
    app = FastAPI()

    @app.post("/v1/test")
    async def limited_endpoint():
        return {"ok": True}

    app.add_middleware(RequestBodyLimitMiddleware)

    with TestClient(app) as client:
        response = client.post("/v1/test", headers={"Content-Length": str(1024 * 1024 + 1)}, content=b"{}")

    assert response.status_code == 413


def test_request_body_limit_middleware_rejects_large_body_after_read(monkeypatch):
    monkeypatch.setattr("middleware.request_limit.settings.request_max_body_mb", 1)
    app = FastAPI()

    @app.post("/v1/test")
    async def limited_endpoint(request: Request):
        await request.body()
        return {"ok": True}

    app.add_middleware(RequestBodyLimitMiddleware)

    with TestClient(app) as client:
        response = client.post("/v1/test", content=b"x" * (1024 * 1024 + 1))

    assert response.status_code == 413
