import asyncio
from contextlib import suppress
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from storage.database import get_session_factory
from storage.models import RuntimeSetting, utc_now

TRAINING_CAPTURE_ENABLED_KEY = "training_capture_enabled"
TRAINING_CAPTURE_ENABLED_DESCRIPTION = "控制是否记录通过请求的训练样本，不影响安全审计"
TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}


@dataclass(slots=True)
class RuntimeSettingsSnapshot:
    training_capture_enabled: bool


class RuntimeSettingsService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None, refresh_interval_seconds: float = 1.0):
        self._session_factory = session_factory or get_session_factory()
        self._refresh_interval_seconds = max(0.1, refresh_interval_seconds)
        self._training_capture_enabled = True
        self._refresh_task: asyncio.Task | None = None
        self._running = False

    @property
    def training_capture_enabled(self) -> bool:
        return self._training_capture_enabled

    async def snapshot(self) -> RuntimeSettingsSnapshot:
        await self.refresh()
        return RuntimeSettingsSnapshot(training_capture_enabled=self._training_capture_enabled)

    async def set_training_capture_enabled(self, enabled: bool, updated_by: str = "") -> RuntimeSettingsSnapshot:
        async with self._session_factory() as session:
            setting = await session.get(RuntimeSetting, TRAINING_CAPTURE_ENABLED_KEY)
            if setting is None:
                setting = RuntimeSetting(
                    key=TRAINING_CAPTURE_ENABLED_KEY,
                    value=_bool_to_value(enabled),
                    description=TRAINING_CAPTURE_ENABLED_DESCRIPTION,
                    updated_by=updated_by,
                )
                session.add(setting)
            else:
                setting.value = _bool_to_value(enabled)
                setting.description = TRAINING_CAPTURE_ENABLED_DESCRIPTION
                setting.updated_by = updated_by
                setting.updated_at = utc_now()
            await session.commit()
        self._training_capture_enabled = enabled
        return RuntimeSettingsSnapshot(training_capture_enabled=enabled)

    async def refresh(self) -> RuntimeSettingsSnapshot:
        try:
            async with self._session_factory() as session:
                result = await session.execute(select(RuntimeSetting).where(RuntimeSetting.key == TRAINING_CAPTURE_ENABLED_KEY))
                setting = result.scalar_one_or_none()
        except Exception:
            return RuntimeSettingsSnapshot(training_capture_enabled=self._training_capture_enabled)
        if setting is None:
            self._training_capture_enabled = True
        else:
            self._training_capture_enabled = _value_to_bool(setting.value, True)
        return RuntimeSettingsSnapshot(training_capture_enabled=self._training_capture_enabled)

    def start(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            return
        self._running = True
        self._refresh_task = asyncio.create_task(self._run_refresh_loop())

    async def stop(self) -> None:
        self._running = False
        if self._refresh_task is None:
            return
        self._refresh_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._refresh_task

    async def _run_refresh_loop(self) -> None:
        while self._running:
            await self.refresh()
            await asyncio.sleep(self._refresh_interval_seconds)


def _value_to_bool(value: str, default: bool) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized == "":
        return default
    return normalized in TRUE_VALUES


def _bool_to_value(value: bool) -> str:
    return "true" if value else "false"
