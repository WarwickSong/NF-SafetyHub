import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from storage import database
from storage.database import POSTGRES_LEGACY_COLUMNS
from storage.models import ApiKeyRecord, ApprovalChain, ApprovalRequest, Base, GeneratedReport, ImageAsset, RuntimeSample, RuntimeSetting, SecurityPolicy


@pytest.mark.asyncio
async def test_stage3_reserved_tables_are_created_with_required_columns():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        table_names = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
        api_key_columns = await conn.run_sync(lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("api_keys")})
        approval_request_columns = await conn.run_sync(lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("approval_requests")})
        image_asset_columns = await conn.run_sync(lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("image_assets")})
        runtime_setting_columns = await conn.run_sync(lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("runtime_settings")})

    assert {
        "audit_logs",
        "api_keys",
        "approval_requests",
        "security_policies",
        "approval_chains",
        "image_assets",
        "runtime_settings",
        "generated_reports",
        "runtime_samples",
    }.issubset(table_names)
    assert {
        "provider_name",
        "upstream_key_id",
        "upstream_key_encrypted",
        "is_decoupled",
        "security_policy_id",
        "approval_chain_id",
        "cost_center",
    }.issubset(api_key_columns)
    assert {"chain_id", "current_level", "escalated_at"}.issubset(approval_request_columns)
    assert {
        "request_id",
        "source_index",
        "source_type",
        "source_url",
        "status",
        "local_path",
        "sha256",
        "mime_type",
        "size_bytes",
        "error",
        "completed_at",
    }.issubset(image_asset_columns)
    assert {"key", "value", "description", "updated_by", "created_at", "updated_at"}.issubset(runtime_setting_columns)

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_db_records_schema_migration_baseline(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    monkeypatch.setattr("storage.database.settings.db_url", "sqlite+aiosqlite:///:memory:")

    await database.init_db()
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT version FROM schema_migrations"))
        versions = {row[0] for row in rows.fetchall()}

    assert "0001_baseline_metadata" in versions

    await engine.dispose()


@pytest.mark.asyncio
async def test_report_tables_are_created_with_required_columns():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        report_columns = await conn.run_sync(lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("generated_reports")})
        sample_columns = await conn.run_sync(lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("runtime_samples")})

    assert {"report_type", "period_start", "period_end", "status", "pdf_path", "xlsx_path", "csv_path", "summary_json", "runtime_summary_json", "expires_at"}.issubset(report_columns)
    assert {"sampled_at", "cpu_percent", "memory_percent", "v1_queued", "archive_queue_size", "data_disk_free", "raw_json"}.issubset(sample_columns)

    await engine.dispose()


def test_postgres_api_keys_legacy_columns_cover_current_model():
    model_columns = set(ApiKeyRecord.__table__.columns.keys())
    preserved_required_columns = model_columns - {"id", "key_hash"}

    assert "api_keys" in POSTGRES_LEGACY_COLUMNS
    assert preserved_required_columns.issubset(POSTGRES_LEGACY_COLUMNS["api_keys"].keys())


@pytest.mark.asyncio
async def test_stage3_reserved_model_defaults_are_safe():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        api_key = ApiKeyRecord(id="key_1", key_hash="hash_1")
        approval = ApprovalRequest(id="approval_1", request_id="req_1")
        policy = SecurityPolicy(id="policy_1", name="default")
        chain = ApprovalChain(id="chain_1", name="default")
        image_asset = ImageAsset(request_id="req_1", source_type="b64_json")
        session.add_all([api_key, approval, policy, chain, image_asset])
        await session.commit()

    async with session_factory() as session:
        stored_key = await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.id == "key_1"))
        stored_approval = await session.scalar(select(ApprovalRequest).where(ApprovalRequest.id == "approval_1"))
        stored_policy = await session.scalar(select(SecurityPolicy).where(SecurityPolicy.id == "policy_1"))
        stored_chain = await session.scalar(select(ApprovalChain).where(ApprovalChain.id == "chain_1"))
        stored_image_asset = await session.scalar(select(ImageAsset).where(ImageAsset.request_id == "req_1"))

    assert stored_key.provider_name == "passthrough"
    assert stored_key.is_decoupled is False
    assert stored_key.security_policy_id is None
    assert stored_key.approval_chain_id is None
    assert stored_approval.current_level == 0
    assert stored_approval.chain_id is None
    assert stored_approval.escalated_at is None
    assert stored_policy.rule_overrides == "{}"
    assert stored_chain.chain_definition == "[]"
    assert stored_image_asset.status == "pending"
    assert stored_image_asset.size_bytes == 0
    assert stored_image_asset.local_path == ""

    await engine.dispose()
