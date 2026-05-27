import asyncio

from storage.database import close_db, init_db


async def main() -> None:
    await init_db()
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
