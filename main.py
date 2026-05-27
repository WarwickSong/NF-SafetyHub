from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import settings, validate_startup_settings
from observability.health import router as health_router
from observability.request_id import RequestIdMiddleware
from storage.database import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_settings(settings)
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.include_router(health_router, prefix="/health", tags=["health"])
