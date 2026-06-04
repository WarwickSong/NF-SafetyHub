import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from admin.router import router as admin_router
from config import settings, validate_startup_settings
from engine.rules_keyword import KeywordScanner
from engine.rules_regex import RegexScanner
from engine.scanner import ScannerOrchestrator
from middleware.auth import AdminStaticAuthMiddleware
from middleware.identity import ApiKeyIdentityMiddleware
from middleware.request_limit import RequestBodyLimitMiddleware
from observability.health import router as health_router
from observability.request_id import RequestIdMiddleware
from proxy.relay import router as relay_router
from proxy.upstream_router import get_default_upstream_router
from storage.database import close_db, get_session_factory, init_db
from governance.api_keys import ApiKeyService
from governance.key_provider import create_key_provider

ADMIN_STATIC_DIR = "admin/static"


async def periodic_rules_reload(scanner: ScannerOrchestrator, interval_seconds: int) -> None:
    interval = max(1, interval_seconds)
    while True:
        await asyncio.sleep(interval)
        with suppress(Exception):
            await scanner.reload_all()


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_settings(settings)
    await init_db()
    scanner = ScannerOrchestrator()
    scanner.register(KeywordScanner(settings.rules_config_path))
    scanner.register(RegexScanner(settings.rules_config_path))
    reload_task = asyncio.create_task(periodic_rules_reload(scanner, settings.rules_reload_interval))
    app.state.scanner = scanner
    app.state.session_factory = get_session_factory()
    app.state.key_provider = create_key_provider(settings)
    app.state.api_key_service = ApiKeyService(app.state.session_factory, key_provider=app.state.key_provider)
    app.state.upstream_router = get_default_upstream_router()
    app.state.rules_reload_task = reload_task
    try:
        yield
    finally:
        reload_task.cancel()
        with suppress(asyncio.CancelledError):
            await reload_task
        await close_db()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(RequestBodyLimitMiddleware)
app.add_middleware(ApiKeyIdentityMiddleware)
app.add_middleware(AdminStaticAuthMiddleware)
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(admin_router, prefix="/admin/api", tags=["admin"])
app.include_router(relay_router, prefix="/v1", tags=["relay"])
app.mount("/admin", StaticFiles(directory=ADMIN_STATIC_DIR, html=True), name="admin")
