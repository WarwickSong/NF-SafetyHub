from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import settings, validate_startup_settings
from engine.rules_keyword import KeywordScanner
from engine.rules_regex import RegexScanner
from engine.scanner import ScannerOrchestrator
from observability.health import router as health_router
from observability.request_id import RequestIdMiddleware
from proxy.relay import router as relay_router
from proxy.upstream_router import get_default_upstream_router
from storage.database import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_settings(settings)
    await init_db()
    scanner = ScannerOrchestrator()
    scanner.register(KeywordScanner(settings.rules_config_path))
    scanner.register(RegexScanner(settings.rules_config_path))
    app.state.scanner = scanner
    app.state.upstream_router = get_default_upstream_router()
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
app.include_router(relay_router, prefix="/v1", tags=["relay"])
