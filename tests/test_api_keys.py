import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from admin.router import router as admin_router
from config import Settings
from engine.rules_keyword import KeywordScanner
from engine.rules_regex import RegexScanner
from engine.scanner import ScannerOrchestrator
from governance.api_keys import ApiKeyCreate, ApiKeyCrypto, ApiKeyService, hash_api_key, parse_bulk_replace_csv
from middleware.identity import ApiKeyIdentityMiddleware
from proxy.relay import router as relay_router
from proxy.upstream_router import UpstreamRouter
from storage.admin_ops import AdminOperationReader, AdminOperationWriter
from storage.models import Base


@pytest.mark.asyncio
async def test_api_key_service_creates_ksync_record_and_replaces_upstream_key():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ApiKeyService(session_factory, ApiKeyCrypto("test-data-key"))

    record = await service.create_ksync(
        ApiKeyCreate(
            name="研发 Key",
            owner_user_id="user_a",
            upstream_key="sk-upstream-original",
        )
    )

    assert record.key_hash == hash_api_key("sk-upstream-original")
    assert record.upstream_key_encrypted != "sk-upstream-original"
    assert record.is_decoupled is False
    assert await service.decrypt_upstream_key(record) == "sk-upstream-original"

    with pytest.raises(ValueError, match="safetyhub api key already exists"):
        await service.create_ksync(
            ApiKeyCreate(
                name="重复 Key",
                owner_user_id="user_b",
                upstream_key="sk-upstream-original",
            )
        )

    updated = await service.replace_upstream_key(record.id, "sk-upstream-new")

    assert updated is not None
    assert updated.key_hash == hash_api_key("sk-upstream-original")
    assert updated.upstream_key_prefix == "sk-upstream-"
    assert updated.is_decoupled is True
    assert await service.decrypt_upstream_key(updated) == "sk-upstream-new"

    await engine.dispose()


@pytest.mark.asyncio
async def test_api_key_service_creates_decoupled_record_with_unique_safetyhub_key():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ApiKeyService(session_factory, ApiKeyCrypto("test-data-key"))

    result = await service.create(
        ApiKeyCreate(
            name="研发 Key",
            owner_user_id="user_a",
            upstream_key="sk-upstream-original",
            reuse_upstream_key=False,
        )
    )

    assert result.safetyhub_key is not None
    assert result.safetyhub_key.startswith("sk-sh-")
    assert result.record.key_hash == hash_api_key(result.safetyhub_key)
    assert result.record.upstream_key_prefix == "sk-upstream-"
    assert result.record.is_decoupled is True
    assert await service.decrypt_upstream_key(result.record) == "sk-upstream-original"

    await engine.dispose()


def test_parse_bulk_replace_csv_supports_id_and_prefix_columns():
    rows = parse_bulk_replace_csv("api_key_id,new_upstream_key\nak_1,sk-new-1\n")
    prefix_rows = parse_bulk_replace_csv("safetyhub_key_prefix,new_upstream_key\nsk-old,sk-new-2\n")

    assert rows[0].identifier == "ak_1"
    assert rows[0].new_upstream_key == "sk-new-1"
    assert prefix_rows[0].identifier == "sk-old"


@pytest.mark.asyncio
async def test_admin_api_key_crud_and_admin_operation_logging():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(admin_router, prefix="/admin/api")
    app.state.settings = Settings(admin_password="strong-local-password")
    app.state.session_factory = session_factory
    app.state.api_key_service = ApiKeyService(session_factory, ApiKeyCrypto("test-data-key"))
    app.state.admin_operation_writer = AdminOperationWriter(session_factory)
    app.state.admin_operation_reader = AdminOperationReader(session_factory)

    with TestClient(app) as client:
        auth = ("admin", "strong-local-password")
        create_response = client.post(
            "/admin/api/api-keys",
            auth=auth,
            json={
                "name": "研发 Key",
                "owner_user_id": "user_a",
                "upstream_key": "sk-upstream-original",
            },
        )
        duplicate_response = client.post(
            "/admin/api/api-keys",
            auth=auth,
            json={
                "name": "研发 Key Duplicate",
                "owner_user_id": "user_b",
                "upstream_key": "sk-upstream-original",
                "reuse_upstream_key": True,
            },
        )
        decoupled_response = client.post(
            "/admin/api/api-keys",
            auth=auth,
            json={
                "name": "研发 Key Decoupled",
                "owner_user_id": "user_c",
                "upstream_key": "sk-upstream-decoupled",
                "reuse_upstream_key": False,
            },
        )
        api_key_id = create_response.json()["item"]["id"]
        list_response = client.get("/admin/api/api-keys", auth=auth)
        detail_response = client.get(f"/admin/api/api-keys/{api_key_id}", auth=auth)
        replace_response = client.post(
            f"/admin/api/api-keys/{api_key_id}/replace-upstream-key",
            auth=auth,
            json={"new_upstream_key": "sk-upstream-new"},
        )
        revoke_response = client.post(f"/admin/api/api-keys/{api_key_id}/revoke", auth=auth)
        operations_response = client.get("/admin/api/admin-ops?resource_type=api_key", auth=auth)

    assert create_response.status_code == 200
    assert duplicate_response.status_code == 400
    assert duplicate_response.json()["detail"] == "safetyhub api key already exists"
    assert decoupled_response.status_code == 200
    assert decoupled_response.json()["safetyhub_key"].startswith("sk-sh-")
    assert decoupled_response.json()["item"]["is_decoupled"] is True
    assert "sk-upstream-decoupled" not in str(decoupled_response.json())
    assert create_response.json()["item"]["is_decoupled"] is False
    assert "sk-upstream-original" not in str(create_response.json())
    assert "model_allowlist" not in create_response.json()["item"]
    assert list_response.json()["pagination"]["total"] == 2
    assert replace_response.json()["item"]["is_decoupled"] is True
    assert revoke_response.json()["item"]["status"] == "revoked"
    assert {item["operation"] for item in operations_response.json()["items"]} >= {
        "api_key.create",
        "api_key.view_detail",
        "api_key.replace_upstream_key",
        "api_key.revoke",
    }

    await engine.dispose()


@pytest.mark.asyncio
async def test_relay_uses_managed_upstream_key_without_enforcing_resource_allowlists(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    service = ApiKeyService(session_factory, ApiKeyCrypto("test-data-key"))
    await service.create_ksync(
        ApiKeyCreate(
            name="研发 Key",
            owner_user_id="user_a",
            upstream_key="sk-client-key",
        )
    )
    record = await service.find_by_raw_key("sk-client-key")
    await service.replace_upstream_key(record.id, "sk-upstream-new")
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured[str(request.url)] = request.headers.get("authorization")
        if str(request.url).endswith("/v1/embeddings"):
            return httpx.Response(200, json={"object": "list", "data": []})
        return httpx.Response(200, json={"id": "chatcmpl-upstream", "object": "chat.completion", "choices": []})

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)
    monkeypatch.setattr("proxy.relay.settings.upstream_url", "https://upstream.example.com")

    app = FastAPI()
    scanner = ScannerOrchestrator()
    scanner.register(KeywordScanner("engine/rules_config.yaml"))
    scanner.register(RegexScanner("engine/rules_config.yaml"))
    app.state.scanner = scanner
    app.state.session_factory = session_factory
    app.state.api_key_service = service
    app.state.upstream_router = UpstreamRouter("https://upstream.example.com")
    app.add_middleware(ApiKeyIdentityMiddleware)
    app.include_router(relay_router, prefix="/v1")

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-client-key"},
            json={"model": "gpt-test", "messages": [{"role": "user", "content": "你好"}]},
        )
        embeddings_response = client.post(
            "/v1/embeddings",
            headers={"Authorization": "Bearer sk-client-key"},
            json={"model": "gpt-test", "input": "hello"},
        )

    assert response.status_code == 200
    assert embeddings_response.status_code == 200
    assert captured["https://upstream.example.com/v1/chat/completions"] == "Bearer sk-upstream-new"
    assert captured["https://upstream.example.com/v1/embeddings"] == "Bearer sk-upstream-new"

    await engine.dispose()
