import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress

from fastapi import FastAPI

from admin.router import router as admin_router
from config import settings, validate_startup_settings
from engine.rules_keyword import KeywordScanner
from engine.rules_regex import RegexScanner
from engine.scanner import ScannerOrchestrator
from middleware.auth import AdminStaticAuthMiddleware, AdminStaticFiles
from middleware.concurrency_limit import V1ConcurrencyLimitMiddleware
from middleware.identity import ApiKeyIdentityMiddleware
from middleware.request_limit import RequestBodyLimitMiddleware
from observability.health import router as health_router
from observability.request_id import RequestIdMiddleware
from proxy.relay import router as relay_router
from proxy.upstream_router import get_default_upstream_router
from runtime.admin_cache import AdminStatsCache
from runtime.archive_queue import ArchiveQueue
from runtime.reports import ReportScheduler, ReportService
from runtime.upstream_client import create_upstream_client
from storage.audit import AuditWriter
from storage.database import close_db, get_session_factory, init_db
from storage.data_governance import DataGovernanceService
from storage.training import TrainingConversationReader, TrainingConversationWriter
from storage.runtime_settings import RuntimeSettingsService
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
    app.state.upstream_client = create_upstream_client()
    app.state.audit_writer = AuditWriter(app.state.session_factory)
    app.state.training_writer = TrainingConversationWriter(app.state.session_factory)
    app.state.training_conversation_reader = TrainingConversationReader(app.state.session_factory)
    app.state.data_governance_service = DataGovernanceService(app.state.session_factory)
    app.state.runtime_settings_service = RuntimeSettingsService(app.state.session_factory)
    await app.state.runtime_settings_service.refresh()
    app.state.runtime_settings_service.start()
    app.state.archive_queue = ArchiveQueue(app.state.audit_writer, app.state.training_writer, runtime_settings=app.state.runtime_settings_service)
    app.state.archive_queue.start()
    app.state.report_service = ReportService(app.state.session_factory, archive_queue=app.state.archive_queue)
    app.state.report_scheduler = ReportScheduler(app.state.report_service)
    app.state.report_scheduler.start()
    app.state.admin_stats_cache = AdminStatsCache()
    app.state.rules_reload_task = reload_task
    try:
        yield
    finally:
        await app.state.report_scheduler.stop()
        await app.state.archive_queue.stop()
        await app.state.runtime_settings_service.stop()
        await app.state.upstream_client.aclose()
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

app.add_middleware(AdminStaticAuthMiddleware)
app.add_middleware(ApiKeyIdentityMiddleware)
app.add_middleware(RequestBodyLimitMiddleware)
app.add_middleware(V1ConcurrencyLimitMiddleware)
app.add_middleware(RequestIdMiddleware)
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(admin_router, prefix="/admin/api", tags=["admin"])
app.include_router(relay_router, prefix="/v1", tags=["relay"])
app.mount("/admin", AdminStaticFiles(directory=ADMIN_STATIC_DIR, html=True), name="admin")
