from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from config import settings
from storage.database import get_session_factory

router = APIRouter()


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> JSONResponse:
    checks = {
        "database": await _check_database(),
        "rules": _check_rules_file(),
    }
    is_ready = all(checks.values())
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={"status": "ready" if is_ready else "not_ready", "checks": checks},
    )


async def _check_database() -> bool:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        return result.scalar_one() == 1


def _check_rules_file() -> bool:
    return Path(settings.rules_config_path).exists()
