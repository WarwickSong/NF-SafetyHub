from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from config import settings
from storage.models import Base

engine: AsyncEngine = create_async_engine(settings.db_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    _ensure_sqlite_parent_dir()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_sqlite_archive_columns(conn)


async def close_db() -> None:
    await engine.dispose()


def get_session_factory() -> async_sessionmaker:
    return SessionLocal


SQLITE_MESSAGE_ARCHIVE_COLUMNS = {
    "prompt_original": "TEXT DEFAULT ''",
    "prompt_desensitized": "TEXT DEFAULT ''",
    "is_desensitized": "BOOLEAN DEFAULT 0",
    "action_taken": "VARCHAR(32) DEFAULT 'passed'",
    "matched_rule_ids": "TEXT DEFAULT ''",
    "image_metadata": "TEXT DEFAULT ''",
}


async def _ensure_sqlite_archive_columns(conn) -> None:
    if not settings.db_url.startswith("sqlite+aiosqlite:///"):
        return
    rows = await conn.execute(text("PRAGMA table_info(message_archives)"))
    existing_columns = {row[1] for row in rows.fetchall()}
    for column_name, column_definition in SQLITE_MESSAGE_ARCHIVE_COLUMNS.items():
        if column_name in existing_columns:
            continue
        await conn.execute(text(f"ALTER TABLE message_archives ADD COLUMN {column_name} {column_definition}"))


def _ensure_sqlite_parent_dir() -> None:
    prefix = "sqlite+aiosqlite:///"
    if not settings.db_url.startswith(prefix):
        return
    db_path = settings.db_url.removeprefix(prefix)
    if db_path.startswith(":memory:"):
        return
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
