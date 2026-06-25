import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from storage.database import close_db, engine, init_db
from storage.models import ApiKeyRecord, Base, RuntimeSetting

PRESERVED_TABLES = {ApiKeyRecord.__tablename__, RuntimeSetting.__tablename__}


async def main() -> None:
    await init_db()
    tables_to_rebuild = [table for table in Base.metadata.sorted_tables if table.name not in PRESERVED_TABLES]
    async with engine.begin() as conn:
        for table in reversed(tables_to_rebuild):
            await conn.execute(text(f'DROP TABLE IF EXISTS "{table.name}" CASCADE'))
        await conn.run_sync(Base.metadata.create_all)
    await close_db()
    print("rebuilt tables: " + ", ".join(table.name for table in tables_to_rebuild))
    print("preserved tables: " + ", ".join(sorted(PRESERVED_TABLES)))
    print("preserved table schemas checked by init_db")


if __name__ == "__main__":
    asyncio.run(main())
