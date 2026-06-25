import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from storage.models import Base
from storage.runtime_settings import RuntimeSettingsService


@pytest.mark.asyncio
async def test_runtime_settings_defaults_training_capture_enabled():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = RuntimeSettingsService(session_factory)
    snapshot = await service.snapshot()

    assert snapshot.training_capture_enabled is True
    assert service.training_capture_enabled is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_runtime_settings_persists_training_capture_toggle():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = RuntimeSettingsService(session_factory)
    disabled = await service.set_training_capture_enabled(False, updated_by="admin")
    reloaded_service = RuntimeSettingsService(session_factory)
    reloaded = await reloaded_service.snapshot()

    assert disabled.training_capture_enabled is False
    assert reloaded.training_capture_enabled is False
    await engine.dispose()
