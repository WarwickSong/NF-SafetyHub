import asyncio
import os

from sqlalchemy.ext.asyncio import create_async_engine

from storage.models import Base


async def main() -> None:
    print("tables_to_create", [table.name for table in Base.metadata.sorted_tables], flush=True)
    engine = create_async_engine(os.environ["POSTGRES_URL"], future=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("create_all_done", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
