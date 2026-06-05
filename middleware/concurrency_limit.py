import asyncio
from time import perf_counter
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config import settings

QUEUE_WAIT_HEADER = "X-SafetyHub-Queue-Wait-Ms"
INFLIGHT_HEADER = "X-SafetyHub-Inflight"
QUEUE_SIZE_HEADER = "X-SafetyHub-Queue-Size"
REJECT_REASON_HEADER = "X-SafetyHub-Reject-Reason"
RETRY_AFTER_HEADER = "Retry-After"
_LAST_MIDDLEWARE: "V1ConcurrencyLimitMiddleware | None" = None


def get_v1_concurrency_snapshot() -> dict[str, Any] | None:
    if _LAST_MIDDLEWARE is None:
        return None
    return _LAST_MIDDLEWARE.snapshot()


class V1ConcurrencyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        max_inflight: int | None = None,
        max_queue_size: int | None = None,
        queue_timeout_seconds: float | None = None,
    ):
        self.app = app
        self._max_inflight = max(1, max_inflight if max_inflight is not None else settings.v1_max_inflight)
        self._max_queue_size = max(0, max_queue_size if max_queue_size is not None else settings.v1_max_queue_size)
        self._queue_timeout_seconds = max(
            0.001,
            queue_timeout_seconds if queue_timeout_seconds is not None else settings.v1_queue_timeout_seconds,
        )
        self._condition = asyncio.Condition()
        self._queued = 0
        self._inflight = 0
        global _LAST_MIDDLEWARE
        _LAST_MIDDLEWARE = self

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not str(scope.get("path", "")).startswith("/v1/"):
            await self.app(scope, receive, send)
            return
        wait_started_at = perf_counter()
        acquired = await self._acquire_slot(wait_started_at, scope, receive, send)
        if acquired is None:
            return
        queue_wait_ms, inflight, queue_size = acquired
        try:
            await self.app(
                scope,
                receive,
                self._build_send_with_headers(send, queue_wait_ms, inflight, queue_size),
            )
        finally:
            async with self._condition:
                self._inflight = max(0, self._inflight - 1)
                self._condition.notify(1)

    async def _acquire_slot(
        self,
        wait_started_at: float,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> tuple[int, int, int] | None:
        queued = False
        async with self._condition:
            if self._inflight >= self._max_inflight:
                if self._queued >= self._max_queue_size:
                    await self._send_reject(scope, receive, send, "queue_full", 0)
                    return None
                self._queued += 1
                queued = True
            try:
                while self._inflight >= self._max_inflight:
                    remaining = self._queue_timeout_seconds - (perf_counter() - wait_started_at)
                    if remaining <= 0:
                        await self._send_reject(scope, receive, send, "queue_timeout", int((perf_counter() - wait_started_at) * 1000))
                        return None
                    try:
                        await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                    except TimeoutError:
                        await self._send_reject(scope, receive, send, "queue_timeout", int((perf_counter() - wait_started_at) * 1000))
                        return None
            finally:
                if queued:
                    self._queued = max(0, self._queued - 1)
            self._inflight += 1
            return int((perf_counter() - wait_started_at) * 1000), self._inflight, self._queued

    def _build_send_with_headers(self, send: Send, queue_wait_ms: int, inflight: int, queue_size: int) -> Send:
        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[QUEUE_WAIT_HEADER] = str(queue_wait_ms)
                headers[INFLIGHT_HEADER] = str(inflight)
                headers[QUEUE_SIZE_HEADER] = str(queue_size)
            await send(message)

        return send_with_headers

    async def _send_reject(self, scope: Scope, receive: Receive, send: Send, reason: str, queue_wait_ms: int) -> None:
        response = JSONResponse(
            status_code=429,
            content={"detail": "too many /v1 requests", "reason": reason},
        )
        response.headers[QUEUE_WAIT_HEADER] = str(queue_wait_ms)
        response.headers[INFLIGHT_HEADER] = str(self._inflight)
        response.headers[QUEUE_SIZE_HEADER] = str(self._queued)
        response.headers[REJECT_REASON_HEADER] = reason
        response.headers[RETRY_AFTER_HEADER] = str(max(1, int(self._queue_timeout_seconds)))
        await response(scope, receive, send)

    def snapshot(self) -> dict[str, Any]:
        return {
            "max_inflight": self._max_inflight,
            "max_queue_size": self._max_queue_size,
            "queue_timeout_seconds": self._queue_timeout_seconds,
            "inflight": self._inflight,
            "queue_size": self._queued,
        }
