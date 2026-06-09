import argparse
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine

from storage.models import Base

DEFAULT_TABLES = [
    "api_keys",
    "message_archives",
    "audit_logs",
    "admin_operations",
    "image_assets",
    "approval_requests",
    "security_policies",
    "approval_chains",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify SafetyHub SQLite to PostgreSQL migration")
    parser.add_argument("--sqlite-path", default="data/safetyhub.db")
    parser.add_argument("--postgres-url", default=os.getenv("POSTGRES_DB_URL", ""))
    parser.add_argument("--tables", default=",".join(DEFAULT_TABLES))
    return parser.parse_args()


def read_sqlite_counts(sqlite_path: str, table_names: list[str]) -> tuple[str, dict[str, int]]:
    connection = sqlite3.connect(Path(sqlite_path))
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        counts = {}
        for table_name in table_names:
            counts[table_name] = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        return integrity, counts
    finally:
        connection.close()


async def read_postgres_counts(postgres_url: str, table_names: list[str]) -> dict[str, int]:
    engine = create_async_engine(postgres_url, future=True)
    try:
        tables_by_name = {table.name: table for table in Base.metadata.sorted_tables}
        async with engine.connect() as connection:
            counts = {}
            for table_name in table_names:
                table = tables_by_name[table_name]
                counts[table_name] = await connection.scalar(select(func.count()).select_from(table))
            return counts
    finally:
        await engine.dispose()


async def main() -> None:
    args = parse_args()
    if not args.postgres_url:
        raise SystemExit("POSTGRES_DB_URL or --postgres-url is required")
    if not args.postgres_url.startswith("postgresql+asyncpg://"):
        raise SystemExit("postgres url must use postgresql+asyncpg://")
    table_names = [item.strip() for item in args.tables.split(",") if item.strip()]
    sqlite_integrity, sqlite_counts = read_sqlite_counts(args.sqlite_path, table_names)
    postgres_counts = await read_postgres_counts(args.postgres_url, table_names)
    print(f"sqlite_integrity={sqlite_integrity}")
    mismatch = False
    for table_name in table_names:
        sqlite_count = sqlite_counts[table_name]
        postgres_count = postgres_counts[table_name]
        status = "OK" if sqlite_count == postgres_count else "MISMATCH"
        print(f"{table_name}: sqlite={sqlite_count} postgres={postgres_count} {status}")
        mismatch = mismatch or sqlite_count != postgres_count
    if sqlite_integrity != "ok" or mismatch:
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
