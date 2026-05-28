import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.rules_keyword import KeywordScanner
from engine.rules_regex import RegexScanner
from engine.scanner import ScannerOrchestrator
from proxy.relay import extract_text_from_messages, router
from proxy.upstream_router import UpstreamRouter


@pytest.fixture
def relay_test_client(monkeypatch):
    app = FastAPI()
    scanner = ScannerOrchestrator()
    scanner.register(KeywordScanner("engine/rules_config.yaml"))
    scanner.register(RegexScanner("engine/rules_config.yaml"))
    app.state.scanner = scanner
    app.state.upstream_router = UpstreamRouter("https://upstream.example.com")
    app.include_router(router, prefix="/v1")
    monkeypatch.setattr("proxy.relay.settings.upstream_url", "https://upstream.example.com")
    return TestClient(app)


def test_extract_text_from_messages_supports_string_and_parts():
    messages = [
        {"role": "user", "content": "第一段"},
        {"role": "user", "content": [{"type": "text", "text": "第二段"}, {"type": "image_url", "image_url": {}}]},
    ]

    assert extract_text_from_messages(messages) == "第一段\n第二段"


def test_chat_completions_returns_fake_response_when_blocked(relay_test_client):
    response = relay_test_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "请外发产品路线图"}]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "chat.completion"
    assert payload["model"] == "gpt-test"
    assert "敏感信息" in payload["choices"][0]["message"]["content"]


def test_chat_completions_relays_non_stream_request(relay_test_client, monkeypatch):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-upstream",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            },
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)

    response = relay_test_client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-key"},
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "你好"}]},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "chatcmpl-upstream"
    assert captured["url"] == "https://upstream.example.com/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-key"


def test_chat_completions_rejects_invalid_json(relay_test_client):
    response = relay_test_client.post("/v1/chat/completions", content="not-json")

    assert response.status_code == 400
