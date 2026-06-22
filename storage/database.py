from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from config import settings
from storage.models import Base


def _sqlite_connect_args() -> dict[str, int]:
    if not settings.db_url.startswith("sqlite+aiosqlite:///"):
        return {}
    return {"timeout": 30}


engine: AsyncEngine = create_async_engine(
    settings.db_url,
    future=True,
    connect_args=_sqlite_connect_args(),
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    _ensure_sqlite_parent_dir()
    async with engine.begin() as conn:
        await _configure_sqlite(conn)
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_legacy_columns(conn)


async def close_db() -> None:
    await engine.dispose()


def get_session_factory() -> async_sessionmaker:
    return SessionLocal


SQLITE_LEGACY_COLUMNS = {
    "image_assets": {
        "request_id": "VARCHAR(64) DEFAULT ''",
        "source_index": "INTEGER DEFAULT 0",
        "source_type": "VARCHAR(32) DEFAULT ''",
        "source_url": "TEXT DEFAULT ''",
        "status": "VARCHAR(32) DEFAULT 'pending'",
        "local_path": "TEXT DEFAULT ''",
        "sha256": "VARCHAR(64) DEFAULT ''",
        "mime_type": "VARCHAR(64) DEFAULT ''",
        "size_bytes": "INTEGER DEFAULT 0",
        "error": "TEXT DEFAULT ''",
        "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "completed_at": "DATETIME DEFAULT NULL",
    },
    "audit_logs": {
        "approval_id": "VARCHAR(64) DEFAULT NULL",
        "security_policy_id": "VARCHAR(64) DEFAULT NULL",
        "context_snippet": "TEXT DEFAULT ''",
        "desensitized_snippet": "TEXT DEFAULT ''",
    },
    "training_conversations": {
        "messages": "TEXT DEFAULT ''",
        "assistant_response": "TEXT DEFAULT ''",
        "trajectory": "TEXT DEFAULT ''",
        "analysis_status": "VARCHAR(32) DEFAULT 'pending'",
        "analyzed_at": "DATETIME DEFAULT NULL",
    },
    "data_governance_jobs": {
        "requested_by": "VARCHAR(128) DEFAULT ''",
        "processed_count": "INTEGER DEFAULT 0",
        "marked_count": "INTEGER DEFAULT 0",
        "deleted_count": "INTEGER DEFAULT 0",
        "cursor_value": "VARCHAR(128) DEFAULT ''",
        "config_snapshot": "TEXT DEFAULT '{}'",
        "error": "TEXT DEFAULT ''",
        "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "finished_at": "DATETIME DEFAULT NULL",
    },
    "api_keys": {
        "key_prefix": "VARCHAR(16) DEFAULT ''",
        "key_suffix": "VARCHAR(8) DEFAULT ''",
        "name": "VARCHAR(128) DEFAULT ''",
        "owner_user_id": "VARCHAR(128) DEFAULT ''",
        "owner_department": "VARCHAR(128) DEFAULT NULL",
        "cost_center": "VARCHAR(64) DEFAULT NULL",
        "status": "VARCHAR(16) DEFAULT 'active'",
        "provider_name": "VARCHAR(64) DEFAULT 'passthrough'",
        "upstream_route_id": "VARCHAR(64) DEFAULT NULL",
        "upstream_key_id": "VARCHAR(128) DEFAULT NULL",
        "upstream_key_prefix": "VARCHAR(16) DEFAULT NULL",
        "upstream_key_encrypted": "TEXT DEFAULT NULL",
        "safetyhub_key_encrypted": "TEXT DEFAULT NULL",
        "is_decoupled": "BOOLEAN DEFAULT 0",
        "security_policy_id": "VARCHAR(64) DEFAULT NULL",
        "approval_chain_id": "VARCHAR(64) DEFAULT NULL",
        "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "expires_at": "DATETIME DEFAULT NULL",
        "revoked_at": "DATETIME DEFAULT NULL",
    },
}


POSTGRES_LEGACY_COLUMNS = {
    "audit_logs": {
        "context_snippet": "TEXT DEFAULT ''",
        "desensitized_snippet": "TEXT DEFAULT ''",
    },
    "api_keys": {
        "key_prefix": "VARCHAR(16) DEFAULT ''",
        "key_suffix": "VARCHAR(8) DEFAULT ''",
        "name": "VARCHAR(128) DEFAULT ''",
        "owner_user_id": "VARCHAR(128) DEFAULT ''",
        "owner_department": "VARCHAR(128) DEFAULT NULL",
        "cost_center": "VARCHAR(64) DEFAULT NULL",
        "status": "VARCHAR(16) DEFAULT 'active'",
        "provider_name": "VARCHAR(64) DEFAULT 'passthrough'",
        "upstream_route_id": "VARCHAR(64) DEFAULT NULL",
        "upstream_key_id": "VARCHAR(128) DEFAULT NULL",
        "upstream_key_prefix": "VARCHAR(16) DEFAULT NULL",
        "upstream_key_encrypted": "TEXT DEFAULT NULL",
        "safetyhub_key_encrypted": "TEXT DEFAULT NULL",
        "is_decoupled": "BOOLEAN DEFAULT false",
        "security_policy_id": "VARCHAR(64) DEFAULT NULL",
        "approval_chain_id": "VARCHAR(64) DEFAULT NULL",
        "created_at": "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP",
        "expires_at": "TIMESTAMP WITH TIME ZONE DEFAULT NULL",
        "revoked_at": "TIMESTAMP WITH TIME ZONE DEFAULT NULL",
    },
    "training_conversations": {
        "messages": "TEXT DEFAULT ''",
        "assistant_response": "TEXT DEFAULT ''",
        "trajectory": "TEXT DEFAULT ''",
        "analysis_status": "VARCHAR(32) DEFAULT 'pending'",
        "analyzed_at": "TIMESTAMP WITH TIME ZONE DEFAULT NULL",
    },
    "data_governance_jobs": {
        "requested_by": "VARCHAR(128) DEFAULT ''",
        "processed_count": "INTEGER DEFAULT 0",
        "marked_count": "INTEGER DEFAULT 0",
        "deleted_count": "INTEGER DEFAULT 0",
        "cursor_value": "VARCHAR(128) DEFAULT ''",
        "config_snapshot": "TEXT DEFAULT '{}'",
        "error": "TEXT DEFAULT ''",
        "updated_at": "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP",
        "finished_at": "TIMESTAMP WITH TIME ZONE DEFAULT NULL",
    },
}


async def _configure_sqlite(conn) -> None:
    if not settings.db_url.startswith("sqlite+aiosqlite:///"):
        return
    await conn.execute(text("PRAGMA journal_mode=WAL"))
    await conn.execute(text("PRAGMA synchronous=NORMAL"))
    await conn.execute(text("PRAGMA busy_timeout=30000"))


async def _ensure_legacy_columns(conn) -> None:
    await _ensure_sqlite_legacy_columns(conn)
    await _ensure_postgres_legacy_columns(conn)


async def _ensure_sqlite_legacy_columns(conn) -> None:
    if not settings.db_url.startswith("sqlite+aiosqlite:///"):
        return
    for table_name, columns in SQLITE_LEGACY_COLUMNS.items():
        rows = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        existing_columns = {row[1] for row in rows.fetchall()}
        for column_name, column_definition in columns.items():
            if column_name in existing_columns:
                continue
            await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"))


async def _ensure_postgres_legacy_columns(conn) -> None:
    if not settings.db_url.startswith("postgresql+asyncpg://"):
        return
    for table_name, columns in POSTGRES_LEGACY_COLUMNS.items():
        for column_name, column_definition in columns.items():
            await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_definition}"))


def _ensure_sqlite_parent_dir() -> None:
    prefix = "sqlite+aiosqlite:///"
    if not settings.db_url.startswith(prefix):
        return
    db_path = settings.db_url.removeprefix(prefix)
    if db_path.startswith(":memory:"):
        return
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
