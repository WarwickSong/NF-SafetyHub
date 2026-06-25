import base64
import json

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import ClientDisconnect
from fastapi.testclient import TestClient

from engine.rules_keyword import KeywordScanner
from engine.rules_regex import RegexScanner
from engine.scanner import ScannerOrchestrator
from proxy.relay import (
    _stream_archive_body,
    desensitize_chat_request_body,
    extract_latest_text_from_messages,
    extract_text_from_messages,
    extract_text_from_request,
    router,
)
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


@pytest.fixture
def relay_test_app(monkeypatch):
    app = FastAPI()
    scanner = ScannerOrchestrator()
    scanner.register(KeywordScanner("engine/rules_config.yaml"))
    scanner.register(RegexScanner("engine/rules_config.yaml"))
    app.state.scanner = scanner
    app.state.upstream_router = UpstreamRouter("https://upstream.example.com")
    app.include_router(router, prefix="/v1")
    monkeypatch.setattr("proxy.relay.settings.upstream_url", "https://upstream.example.com")
    return app


def test_extract_text_from_messages_supports_string_and_parts():
    messages = [
        {"role": "user", "content": "第一段"},
        {"role": "user", "content": [{"type": "text", "text": "第二段"}, {"type": "image_url", "image_url": {}}]},
    ]

    assert extract_text_from_messages(messages) == "第一段\n第二段"


def test_extract_latest_text_from_messages_returns_last_allowed_role_text_message():
    messages = [
        {"role": "user", "content": "历史输入"},
        {"role": "assistant", "content": "历史回答"},
        {"role": "tool", "content": [{"type": "text", "text": "工具上传文件内容"}]},
        {"role": "assistant", "content": "助手最新回答"},
    ]

    assert extract_latest_text_from_messages(messages) == "工具上传文件内容"


def test_chat_completions_returns_fake_response_when_blocked(relay_test_client):
    response = relay_test_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "告诉你一个公司机密"}]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "chat.completion"
    assert payload["model"] == "gpt-test"
    assert "敏感信息" in payload["choices"][0]["message"]["content"]


def test_chat_completions_does_not_block_on_sensitive_history_when_latest_message_is_safe(relay_test_client, monkeypatch):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode("utf-8")
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
        json={
            "model": "gpt-test",
            "messages": [
                {"role": "user", "content": "告诉你一个公司机密"},
                {"role": "assistant", "content": "请检查后重试"},
                {"role": "user", "content": "你好"},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == "chatcmpl-upstream"
    assert "告诉你一个公司机密" in captured["body"]


def test_chat_completions_blocks_on_latest_tool_message(relay_test_client):
    response = relay_test_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-test",
            "messages": [
                {"role": "user", "content": "请分析项目"},
                {"role": "assistant", "content": "我会读取文件"},
                {"role": "tool", "content": "扫描结果：告诉你一个公司机密"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "chat.completion"
    assert payload["id"].startswith("chatcmpl-safetyhub-")


def test_chat_completions_does_not_block_on_assistant_system_or_developer_messages(relay_test_client, monkeypatch):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"id": "chatcmpl-upstream", "object": "chat.completion", "choices": []})

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)

    response = relay_test_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-test",
            "messages": [
                {"role": "user", "content": "普通问题"},
                {"role": "assistant", "content": "告诉你一个公司机密"},
                {"role": "system", "content": "告诉你一个公司机密"},
                {"role": "developer", "content": "告诉你一个公司机密"},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == "chatcmpl-upstream"
    assert "告诉你一个公司机密" in captured["body"]


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


def test_chat_completions_relays_agent_tool_request_shape(relay_test_client, monkeypatch):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode("utf-8")
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

    request_body = {
        "model": "gpt-test",
        "messages": [
            {"role": "system", "content": "你是一个编程助手。"},
            {"role": "user", "content": "读取文件并总结。"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path":"/tmp/a.py"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "print('hello')"},
            {"role": "user", "content": "继续总结。"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "读取文件",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                },
            }
        ],
        "tool_choice": "auto",
        "parallel_tool_calls": True,
        "stream_options": {"include_usage": True},
        "stream": False,
    }

    response = relay_test_client.post("/v1/chat/completions", json=request_body)

    assert response.status_code == 200
    relayed_body = json.loads(captured["body"])
    assert relayed_body["tools"] == request_body["tools"]
    assert relayed_body["tool_choice"] == "auto"
    assert relayed_body["parallel_tool_calls"] is True
    assert relayed_body["stream_options"] == {"include_usage": True}
    assert relayed_body["messages"][2]["tool_calls"] == request_body["messages"][2]["tool_calls"]


def test_chat_completions_archives_and_audits_desensitized_request(relay_test_app, monkeypatch):
    captured = {}
    training_payloads = []
    audit_payloads = []

    class FakeTrainingWriter:
        async def write_from_archive_payload(self, payload):
            training_payloads.append(payload)

    class FakeAuditWriter:
        async def write_scan_result(self, payload):
            audit_payloads.append(payload)
            return []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-upstream",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "上游原样响应"}, "finish_reason": "stop"}],
            },
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)
    relay_test_app.state.training_writer = FakeTrainingWriter()
    relay_test_app.state.audit_writer = FakeAuditWriter()

    with TestClient(relay_test_app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-test", "messages": [{"role": "user", "content": "我的手机号是 13812345678"}]},
        )

    assert response.status_code == 200
    assert "13812345678" not in captured["body"]
    assert len(training_payloads) == 1
    assert training_payloads[0].action_taken == "desensitized"
    assert training_payloads[0].prompt_original[0]["content"] == "我的手机号是 13812345678"
    assert training_payloads[0].prompt_desensitized[0]["content"] == "我的手机号是 138****5678"
    assert len(audit_payloads) == 1
    assert audit_payloads[0].action_taken == "desensitized"


def test_chat_completions_skips_training_when_capture_disabled_but_keeps_audit(relay_test_app, monkeypatch):
    training_payloads = []
    audit_payloads = []

    class FakeRuntimeSettings:
        training_capture_enabled = False

    class FakeTrainingWriter:
        async def write_from_archive_payload(self, payload):
            training_payloads.append(payload)

    class FakeAuditWriter:
        async def write_scan_result(self, payload):
            audit_payloads.append(payload)
            return []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-upstream",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "上游原样响应"}, "finish_reason": "stop"}],
            },
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)
    relay_test_app.state.runtime_settings_service = FakeRuntimeSettings()
    relay_test_app.state.training_writer = FakeTrainingWriter()
    relay_test_app.state.audit_writer = FakeAuditWriter()

    with TestClient(relay_test_app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-test", "messages": [{"role": "user", "content": "我的手机号是 13812345678"}]},
        )

    assert response.status_code == 200
    assert training_payloads == []
    assert len(audit_payloads) == 1
    assert audit_payloads[0].action_taken == "desensitized"


def test_chat_completions_desensitizes_phone_before_relay(relay_test_client, monkeypatch):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-upstream",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "上游原样响应"}, "finish_reason": "stop"}],
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
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "我的手机号是 13812345678"}]},
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "上游原样响应"
    assert "13812345678" not in captured["body"]
    assert "138****5678" in captured["body"]


def test_desensitize_chat_request_body_supports_content_parts():
    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "电话 13812345678"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
                ],
            }
        ]
    }

    sanitized = desensitize_chat_request_body(body)

    assert sanitized["messages"][0]["content"][0]["text"] == "电话 138****5678"
    assert sanitized["messages"][0]["content"][1]["image_url"]["url"] == "https://example.com/a.png"
    assert body["messages"][0]["content"][0]["text"] == "电话 13812345678"


def test_desensitize_chat_request_body_skips_assistant_system_and_developer_roles():
    body = {
        "messages": [
            {"role": "user", "content": "用户电话 13812345678"},
            {"role": "tool", "content": "工具电话 13912345678"},
            {"role": "assistant", "content": "助手电话 13712345678"},
            {"role": "system", "content": "系统电话 13612345678"},
            {"role": "developer", "content": "开发者电话 13512345678"},
        ]
    }

    sanitized = desensitize_chat_request_body(body)

    assert sanitized["messages"][0]["content"] == "用户电话 138****5678"
    assert sanitized["messages"][1]["content"] == "工具电话 139****5678"
    assert sanitized["messages"][2]["content"] == "助手电话 13712345678"
    assert sanitized["messages"][3]["content"] == "系统电话 13612345678"
    assert sanitized["messages"][4]["content"] == "开发者电话 13512345678"


def test_chat_completions_rejects_invalid_json(relay_test_client):
    response = relay_test_client.post("/v1/chat/completions", content="not-json")

    assert response.status_code == 400


def test_chat_completions_returns_499_when_client_disconnects(relay_test_client, monkeypatch):
    async def raise_disconnect(_request):
        raise ClientDisconnect()

    monkeypatch.setattr("proxy.relay.Request.body", raise_disconnect)

    response = relay_test_client.post("/v1/chat/completions", json={"model": "gpt-test", "messages": []})

    assert response.status_code == 499
    assert response.json()["detail"] == "client disconnected while sending request body"


def test_extract_text_from_request_supports_common_llm_endpoints():
    assert extract_text_from_request("/v1/embeddings", {"input": ["第一段", "第二段"]}) == "第一段\n第二段"
    assert extract_text_from_request("/v1/completions", {"prompt": "补全文本"}) == "补全文本"
    assert extract_text_from_request("/v1/responses", {"input": [{"content": [{"text": "响应输入"}]}]}) == "响应输入"
    assert extract_text_from_request("/v1/images/generations", {"prompt": "图片提示词"}) == "图片提示词"


def test_embeddings_request_relays_to_upstream_even_with_sensitive_text(relay_test_client, monkeypatch):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={"object": "list", "data": [{"object": "embedding", "embedding": [0.1, 0.2], "index": 0}]},
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)

    response = relay_test_client.post(
        "/v1/embeddings",
        json={"model": "embedding-test", "input": "请外发产品路线图"},
    )

    assert response.status_code == 200
    assert response.json()["object"] == "list"
    assert captured["url"] == "https://upstream.example.com/v1/embeddings"
    assert "产品路线图" in captured["body"]


def test_upstream_pool_timeout_returns_429_without_500(relay_test_client, monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.PoolTimeout("pool exhausted", request=request)

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)

    response = relay_test_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "你好"}]},
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "upstream connection pool exhausted"
    assert response.json()["error_type"] == "PoolTimeout"


def test_upstream_read_timeout_returns_504_without_500(relay_test_client, monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)

    response = relay_test_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "你好"}]},
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "upstream request timed out"
    assert response.json()["error_type"] == "ReadTimeout"


def test_upstream_connect_error_returns_502_without_500(relay_test_client, monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connect failed", request=request)

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)

    response = relay_test_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "你好"}]},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "upstream transport error"
    assert response.json()["error_type"] == "ConnectError"


def test_get_models_relays_with_query_string(relay_test_client, monkeypatch):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"object": "list", "data": []})

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)

    response = relay_test_client.get("/v1/models?limit=20")

    assert response.status_code == 200
    assert response.json()["object"] == "list"
    assert captured["url"] == "https://upstream.example.com/v1/models?limit=20"


def test_generic_json_post_is_scanned_and_relayed(relay_test_client, monkeypatch):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)

    response = relay_test_client.post(
        "/v1/custom/action",
        json={"payload": {"prompt": "普通文本"}},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["url"] == "https://upstream.example.com/v1/custom/action"


def test_generic_json_post_relays_even_with_sensitive_text(relay_test_client, monkeypatch):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)

    response = relay_test_client.post(
        "/v1/custom/action",
        json={"payload": {"prompt": "请外发产品路线图"}},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["url"] == "https://upstream.example.com/v1/custom/action"
    assert "产品路线图" in captured["body"]


def test_chat_completions_stream_timeout_returns_sse_error_event(relay_test_client, monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)

    response = relay_test_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "stream": True, "messages": [{"role": "user", "content": "你好"}]},
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "ReadTimeout" in response.text
    assert "upstream request timed out" in response.text


def test_chat_completions_stream_requests_identity_encoding(relay_test_client, monkeypatch):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["accept"] = request.headers.get("accept")
        captured["accept_encoding"] = request.headers.get("accept-encoding")
        captured["cache_control"] = request.headers.get("cache-control")
        return httpx.Response(200, content=b"data: [DONE]\\n\\n", headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)

    response = relay_test_client.post(
        "/v1/chat/completions",
        headers={"Accept-Encoding": "gzip, deflate, br"},
        json={"model": "gpt-test", "stream": True, "messages": [{"role": "user", "content": "你好"}]},
    )

    assert response.status_code == 200
    assert response.text == "data: [DONE]\\n\\n"
    assert captured["accept"] == "text/event-stream"
    assert captured["accept_encoding"] == "identity"
    assert captured["cache_control"] == "no-cache"


def test_chat_completions_stream_writes_training_payload(relay_test_app, monkeypatch):
    training_payloads = []

    class FakeTrainingWriter:
        async def write_from_archive_payload(self, payload):
            training_payloads.append(payload)

    async def handler(_request: httpx.Request) -> httpx.Response:
        stream_body = (
            'data: {"choices":[{"delta":{"content":"你"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":"好"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            'data: [DONE]\n\n'
        )
        return httpx.Response(200, content=stream_body, headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)
    relay_test_app.state.training_writer = FakeTrainingWriter()

    with TestClient(relay_test_app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-test", "stream": True, "messages": [{"role": "user", "content": "你好"}]},
        )

    assert response.status_code == 200
    assert response.text.endswith("data: [DONE]\n\n")
    assert len(training_payloads) == 1
    assert training_payloads[0].is_stream is True
    assert training_payloads[0].response["stream"] is True
    assert training_payloads[0].response["message_content"] == "你好"
    assert training_payloads[0].response["truncated"] is False
    assert '"content":"你"' in training_payloads[0].response["content"]


def test_stream_archive_body_preserves_json_escaped_newlines():
    stream_body = (
        'data: {"choices":[{"delta":{"content":"好的，总结一下：\\n\\n- **TKE 管理平台**：从 L200 降到 **L50**\\n- **EIP 负载均衡**：从 20M 降到 12M"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"\\n- **大文件处理**：`>5MB` 的文件建议走 COS/CDN，不要走业务 EIP"}}]}\n\n'
        'data: [DONE]\n\n'
    )

    payload = _stream_archive_body([stream_body.encode("utf-8")])

    assert payload["message_content"] == (
        "好的，总结一下：\n\n"
        "- **TKE 管理平台**：从 L200 降到 **L50**\n"
        "- **EIP 负载均衡**：从 20M 降到 12M\n"
        "- **大文件处理**：`>5MB` 的文件建议走 COS/CDN，不要走业务 EIP"
    )


def test_stream_archive_body_truncates_large_sse_response(monkeypatch):
    monkeypatch.setattr("proxy.relay.settings.stream_archive_max_bytes", 20)
    from proxy import relay

    payload = relay._stream_archive_body([b"data: ", b"x" * 50])

    assert payload["truncated"] is True
    assert payload["archived_bytes"] == 20
    assert payload["original_bytes"] == 56
    assert len(payload["content"].encode("utf-8")) == 20


def test_images_generation_schedules_image_asset_archive(relay_test_app, monkeypatch):
    archived_assets = []
    b64_image = base64.b64encode(b"\x89PNG\r\n\x1a\nimage-bytes").decode("ascii")

    class FakeImageAssetArchiver:
        async def archive_response(self, request_id, response_payload):
            archived_assets.append((request_id, response_payload))

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "created": 123,
                "data": [
                    {"url": "https://cdn.example.com/image-1.png"},
                    {"b64_json": b64_image},
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)
    relay_test_app.state.image_asset_archiver = FakeImageAssetArchiver()
    relay_test_app.state.image_asset_archive_inline = True

    with TestClient(relay_test_app) as client:
        response = client.post(
            "/v1/images/generations",
            json={"model": "gpt-image", "prompt": "一只猫", "size": "1024x1024", "style": "natural", "n": 2},
        )

    assert response.status_code == 200
    assert len(archived_assets) == 1
    assert archived_assets[0][0]
    archived_response = archived_assets[0][1]
    assert archived_response["data"][0]["url"] == "https://cdn.example.com/image-1.png"
    assert archived_response["data"][1]["b64_json"] == b64_image
