import asyncio

from sqlalchemy import text

from storage.database import close_db, engine
from storage.models import ApiKeyRecord, Base

PRESERVED_TABLES = {ApiKeyRecord.__tablename__}


async def main() -> None:
    tables_to_rebuild = [table for table in Base.metadata.sorted_tables if table.name not in PRESERVED_TABLES]
    async with engine.begin() as conn:
        for table in reversed(tables_to_rebuild):
            await conn.execute(text(f'DROP TABLE IF EXISTS "{table.name}" CASCADE'))
        await conn.run_sync(Base.metadata.create_all)
    await close_db()
    print("rebuilt tables: " + ", ".join(table.name for table in tables_to_rebuild))
    print("preserved tables: " + ", ".join(sorted(PRESERVED_TABLES)))


if __name__ == "__main__":
    asyncio.run(main())
