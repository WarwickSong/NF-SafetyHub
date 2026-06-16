import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from admin.router import router as admin_router
from config import Settings, validate_startup_settings
from engine.rules_keyword import KeywordScanner
from engine.rules_regex import RegexScanner
from engine.scanner import ScannerOrchestrator
from governance.api_keys import ApiKeyCreate, ApiKeyCrypto, ApiKeyService, hash_api_key, parse_bulk_replace_csv
from governance.key_provider import KeyCreateParams, KeyProvider, KeyProviderError, UpstreamKeyInfo
from middleware.identity import ApiKeyIdentityMiddleware
from middleware.request_limit import RequestBodyLimitMiddleware
from proxy.relay import router as relay_router
from proxy.upstream_router import UpstreamRouter
from storage.admin_ops import AdminOperationReader, AdminOperationWriter
from storage.models import Base


class FakeKeyProvider(KeyProvider):
    def __init__(self, fail_revoke: bool = False):
        self.created = []
        self.revoked = []
        self.fail_revoke = fail_revoke

    @property
    def provider_name(self) -> str:
        return "oneapi_nanfu_yxai"

    @property
    def upstream_base_url(self) -> str:
        return "https://yxai-api.nanfu.com"

    async def create_key(self, params: KeyCreateParams) -> UpstreamKeyInfo:
        self.created.append(params)
        return UpstreamKeyInfo(key_id="63", key_prefix="sk-provider", key_suffix="cret-1", key_secret="sk-provider-secret-1")

    async def revoke_key(self, key_id: str) -> bool:
        if self.fail_revoke:
            raise KeyProviderError("revoke failed")
        self.revoked.append(key_id)
        return True

    async def get_key_info(self, key_id: str) -> UpstreamKeyInfo | None:
        return None

    async def list_keys(self) -> list[UpstreamKeyInfo]:
        return []


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
    assert record.safetyhub_key_encrypted != "sk-upstream-original"
    assert record.upstream_key_encrypted.startswith("v2:")
    assert record.safetyhub_key_encrypted.startswith("v2:")
    assert record.is_decoupled is False
    assert await service.decrypt_upstream_key(record) == "sk-upstream-original"
    assert await service.decrypt_safetyhub_key(record) == "sk-upstream-original"

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
    assert await service.decrypt_safetyhub_key(result.record) == result.safetyhub_key

    await engine.dispose()


def test_api_key_crypto_rejects_non_fernet_values():
    crypto = ApiKeyCrypto("test-data-key")

    with pytest.raises(ValueError, match="unsupported encrypted value version"):
        crypto.decrypt("v1:legacy-value")


def test_parse_bulk_replace_csv_supports_id_and_prefix_columns():
    rows = parse_bulk_replace_csv("api_key_id,new_upstream_key\nak_1,sk-new-1\n")
    prefix_rows = parse_bulk_replace_csv("safetyhub_key_prefix,new_upstream_key\nsk-old,sk-new-2\n")

    assert rows[0].identifier == "ak_1"
    assert rows[0].new_upstream_key == "sk-new-1"
    assert prefix_rows[0].identifier == "sk-old"


@pytest.mark.asyncio
async def test_provider_create_reveal_and_revoke():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    provider = FakeKeyProvider()
    service = ApiKeyService(session_factory, ApiKeyCrypto("test-data-key"), provider)

    result = await service.create(
        ApiKeyCreate(
            name="Provider Key",
            owner_user_id="user_provider",
            create_mode="provider",
        )
    )

    assert result.safetyhub_key == "sk-provider-secret-1"
    assert result.record.provider_name == "oneapi_nanfu_yxai"
    assert result.record.upstream_key_id == "63"
    assert result.record.is_decoupled is False
    assert await service.reveal_safetyhub_key(result.record.id) == "sk-provider-secret-1"
    revoked = await service.revoke(result.record.id)
    assert revoked.status == "revoked"
    assert provider.revoked == ["63"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_provider_revoke_failure_does_not_mark_local_record_revoked():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    provider = FakeKeyProvider(fail_revoke=True)
    service = ApiKeyService(session_factory, ApiKeyCrypto("test-data-key"), provider)
    result = await service.create(ApiKeyCreate(name="Provider Key", owner_user_id="user_provider", create_mode="provider"))

    with pytest.raises(KeyProviderError, match="revoke failed"):
        await service.revoke(result.record.id)

    record = await service.get(result.record.id)
    assert record.status == "active"

    await engine.dispose()


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
        reveal_response = client.post(f"/admin/api/api-keys/{api_key_id}/reveal", auth=auth)
        delete_active_response = client.delete(f"/admin/api/api-keys/{api_key_id}", auth=auth)
        revoke_response = client.post(f"/admin/api/api-keys/{api_key_id}/revoke", auth=auth)
        delete_response = client.delete(f"/admin/api/api-keys/{api_key_id}", auth=auth)
        list_after_delete_response = client.get("/admin/api/api-keys", auth=auth)
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
    assert reveal_response.status_code == 200
    assert reveal_response.json()["key"] == "sk-upstream-original"
    assert reveal_response.headers["cache-control"] == "no-store"
    assert delete_active_response.status_code == 400
    assert delete_active_response.json()["detail"] == "only revoked api key can be deleted"
    assert revoke_response.json()["item"]["status"] == "revoked"
    assert delete_response.status_code == 200
    assert delete_response.json()["api_key_id"] == api_key_id
    assert list_after_delete_response.json()["pagination"]["total"] == 1
    assert {item["operation"] for item in operations_response.json()["items"]} >= {
        "api_key.create",
        "api_key.view_detail",
        "api_key.replace_upstream_key",
        "api_key.reveal",
        "api_key.revoke",
        "api_key.delete",
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


@pytest.mark.asyncio
async def test_api_key_middleware_returns_401_instead_of_500_when_key_missing(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ApiKeyService(session_factory=session_factory, crypto=ApiKeyCrypto("test-data-key"))
    await service.create(ApiKeyCreate(name="client", owner_user_id="user-1", upstream_key="sk-upstream"))
    monkeypatch.setattr("middleware.identity.settings.allow_empty_api_keys_passthrough", False)

    app = FastAPI()
    app.state.api_key_service = service
    app.state.session_factory = session_factory

    @app.get("/v1/test")
    async def protected_endpoint():
        return {"ok": True}

    app.add_middleware(ApiKeyIdentityMiddleware, api_key_count_cache_seconds=0)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/v1/test")

    assert response.status_code == 401
    assert response.json()["detail"] == "missing api key"

    await engine.dispose()


def test_production_startup_validation_requires_data_key_and_disables_empty_key_passthrough(monkeypatch):
    monkeypatch.delenv("SAFETYHUB_DATA_KEY", raising=False)
    production_settings = Settings(
        environment="production",
        upstream_url="https://upstream.example.com",
        admin_password="strong-local-password",
        allow_empty_api_keys_passthrough=True,
    )

    with pytest.raises(RuntimeError) as exc_info:
        validate_startup_settings(production_settings)

    message = str(exc_info.value)
    assert "SAFETYHUB_DATA_KEY" in message
    assert "ALLOW_EMPTY_API_KEYS_PASSTHROUGH=false" in message


def test_settings_get_secret_reads_env_file_named_secret(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("KEY_PROVIDER_PASSWORD=from-env-file\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("KEY_PROVIDER_PASSWORD", raising=False)

    active_settings = Settings(key_provider_password_env="KEY_PROVIDER_PASSWORD")

    assert active_settings.get_secret("KEY_PROVIDER_PASSWORD") == "from-env-file"


def test_settings_get_secret_reads_project_env_when_started_outside_project(tmp_path, monkeypatch):
    cwd = tmp_path / "runtime"
    project = tmp_path / "project"
    cwd.mkdir()
    project.mkdir()
    (project / ".env").write_text("KEY_PROVIDER_PASSWORD=from-project-env\n", encoding="utf-8")
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("KEY_PROVIDER_PASSWORD", raising=False)
    monkeypatch.setattr("config.__file__", str(project / "config.py"))

    active_settings = Settings(key_provider_password_env="KEY_PROVIDER_PASSWORD")

    assert active_settings.get_secret("KEY_PROVIDER_PASSWORD") == "from-project-env"


@pytest.mark.asyncio
async def test_api_key_middleware_rejects_empty_table_when_passthrough_disabled(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ApiKeyService(session_factory=session_factory, crypto=ApiKeyCrypto("test-data-key"))
    monkeypatch.setattr("middleware.identity.settings.allow_empty_api_keys_passthrough", False)

    app = FastAPI()
    app.state.api_key_service = service
    app.add_middleware(ApiKeyIdentityMiddleware, api_key_count_cache_seconds=0)

    @app.get("/v1/test")
    async def protected_endpoint():
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/v1/test", headers={"Authorization": "Bearer sk-client"})

    assert response.status_code == 401
    assert response.json()["detail"] == "api key is required"

    await engine.dispose()


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
