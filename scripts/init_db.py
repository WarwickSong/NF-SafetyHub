import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from storage.database import close_db, init_db


async def main() -> None:
    await init_db()
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
