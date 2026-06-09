import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_project_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_project_env()

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from storage.models import Base

DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./data/safetyhub.db"
DEFAULT_BATCH_SIZE = 1000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate SafetyHub data from SQLite to PostgreSQL")
    parser.add_argument("--sqlite-url", default=os.getenv("SQLITE_DB_URL", DEFAULT_SQLITE_URL))
    parser.add_argument("--postgres-url", default=os.getenv("POSTGRES_DB_URL", ""))
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("MIGRATION_BATCH_SIZE", str(DEFAULT_BATCH_SIZE))))
    parser.add_argument("--replace-target", action="store_true")
    parser.add_argument("--tables", default=os.getenv("MIGRATION_TABLES", ""))
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if not args.postgres_url:
        raise SystemExit("POSTGRES_DB_URL or --postgres-url is required")
    if not args.postgres_url.startswith("postgresql+asyncpg://"):
        raise SystemExit("postgres url must use postgresql+asyncpg://")
    sqlite_engine = create_async_engine(args.sqlite_url, future=True, connect_args={"timeout": 30})
    postgres_engine = create_async_engine(args.postgres_url, future=True)
    try:
        tables = selected_tables(args.tables)
        await create_target_schema(postgres_engine)
        if args.replace_target:
            await clear_target_tables(postgres_engine, tables)
        for table in tables:
            count = await migrate_table(sqlite_engine, postgres_engine, table, max(1, args.batch_size))
            print(f"{table.name}: migrated {count} rows")
        await refresh_postgres_sequences(postgres_engine, tables)
    finally:
        await sqlite_engine.dispose()
        await postgres_engine.dispose()


def selected_tables(table_names: str):
    tables = Base.metadata.sorted_tables
    if not table_names.strip():
        return tables
    wanted = {item.strip() for item in table_names.split(",") if item.strip()}
    unknown = wanted - {table.name for table in tables}
    if unknown:
        raise SystemExit(f"unknown tables: {', '.join(sorted(unknown))}")
    return [table for table in tables if table.name in wanted]


async def create_target_schema(postgres_engine: AsyncEngine) -> None:
    async with postgres_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def clear_target_tables(postgres_engine: AsyncEngine, tables) -> None:
    async with postgres_engine.begin() as conn:
        for table in reversed(tables):
            await conn.execute(delete(table))


async def migrate_table(sqlite_engine: AsyncEngine, postgres_engine: AsyncEngine, table, batch_size: int) -> int:
    total = 0
    offset = 0
    columns = list(table.columns)
    while True:
        async with sqlite_engine.connect() as conn:
            result = await conn.execute(select(*columns).limit(batch_size).offset(offset))
            rows = [dict(row._mapping) for row in result.fetchall()]
        if not rows:
            return total
        await insert_rows(postgres_engine, table, rows)
        total += len(rows)
        offset += len(rows)


async def insert_rows(postgres_engine: AsyncEngine, table, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    async with postgres_engine.begin() as conn:
        await conn.execute(insert(table), rows)


async def refresh_postgres_sequences(postgres_engine: AsyncEngine, tables) -> None:
    async with postgres_engine.begin() as conn:
        for table in tables:
            primary_keys = list(table.primary_key.columns)
            if len(primary_keys) != 1:
                continue
            column = primary_keys[0]
            if not getattr(column.type, "python_type", None) is int:
                continue
            max_id = await conn.scalar(select(func.max(column)))
            if max_id is None:
                continue
            await conn.execute(
                text("SELECT setval(pg_get_serial_sequence(:table_name, :column_name), :max_id, true)"),
                {"table_name": table.name, "column_name": column.name, "max_id": max_id},
            )


if __name__ == "__main__":
    asyncio.run(main())
