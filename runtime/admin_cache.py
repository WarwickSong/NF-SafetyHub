import asyncio
import time
from typing import Awaitable, Callable, TypeVar

from config import settings

T = TypeVar("T")


class AdminStatsCache:
    def __init__(self, ttl_seconds: float | None = None):
        self._ttl_seconds = max(0, ttl_seconds if ttl_seconds is not None else settings.admin_stats_cache_seconds)
        self._expires_at = 0.0
        self._value = None
        self._lock = asyncio.Lock()

    async def get_or_set(self, loader: Callable[[], Awaitable[T]]) -> T:
        now = time.monotonic()
        if self._value is not None and now < self._expires_at:
            return self._value
        async with self._lock:
            now = time.monotonic()
            if self._value is not None and now < self._expires_at:
                return self._value
            value = await loader()
            self._value = value
            self._expires_at = now + self._ttl_seconds
            return value

    def clear(self) -> None:
        self._value = None
        self._expires_at = 0.0
