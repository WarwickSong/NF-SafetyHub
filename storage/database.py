from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from config import settings
from storage.models import Base

engine: AsyncEngine = create_async_engine(settings.db_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    _ensure_sqlite_parent_dir()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    await engine.dispose()


def get_session_factory() -> async_sessionmaker:
    return SessionLocal


def _ensure_sqlite_parent_dir() -> None:
    prefix = "sqlite+aiosqlite:///"
    if not settings.db_url.startswith(prefix):
        return
    db_path = settings.db_url.removeprefix(prefix)
    if db_path.startswith(":memory:"):
        return
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
