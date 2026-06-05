import asyncio

import httpx
import pytest

from middleware.concurrency_limit import (
    INFLIGHT_HEADER,
    QUEUE_SIZE_HEADER,
    QUEUE_WAIT_HEADER,
    REJECT_REASON_HEADER,
    RETRY_AFTER_HEADER,
    V1ConcurrencyLimitMiddleware,
)


class ImmediateAsgiApp:
    async def __call__(self, scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b'{"ok":true}'})


class BlockingAsgiApp:
    def __init__(self):
        self.entered = 0
        self.entered_event = asyncio.Event()
        self.release_event = asyncio.Event()

    async def __call__(self, scope, receive, send):
        self.entered += 1
        self.entered_event.set()
        if self.entered == 1:
            await self.release_event.wait()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b'{"ok":true}'})


class AlwaysBlockingAsgiApp:
    def __init__(self):
        self.entered = 0
        self.entered_event = asyncio.Event()
        self.release_event = asyncio.Event()

    async def __call__(self, scope, receive, send):
        self.entered += 1
        self.entered_event.set()
        await self.release_event.wait()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b'{"ok":true}'})


async def _client(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _wait_for_queue_size(middleware: V1ConcurrencyLimitMiddleware, expected: int) -> None:
    for _ in range(100):
        if middleware.snapshot()["queue_size"] == expected:
            return
        await asyncio.sleep(0.001)
    raise AssertionError(f"queue_size did not become {expected}")


@pytest.mark.asyncio
async def test_v1_concurrency_limit_adds_observability_headers():
    app = ImmediateAsgiApp()
    middleware = V1ConcurrencyLimitMiddleware(app, max_inflight=1, max_queue_size=1, queue_timeout_seconds=1)

    async with await _client(middleware) as client:
        response = await client.get("/v1/test")

    assert response.status_code == 200
    assert response.headers[QUEUE_WAIT_HEADER].isdigit()
    assert response.headers[INFLIGHT_HEADER] == "1"
    assert response.headers[QUEUE_SIZE_HEADER] == "0"


@pytest.mark.asyncio
async def test_concurrency_limit_only_applies_to_v1_paths():
    app = AlwaysBlockingAsgiApp()
    middleware = V1ConcurrencyLimitMiddleware(app, max_inflight=1, max_queue_size=0, queue_timeout_seconds=0.01)

    async with await _client(middleware) as client:
        request_task = asyncio.create_task(client.get("/admin/test"))
        await app.entered_event.wait()
        assert middleware.snapshot()["inflight"] == 0
        app.release_event.set()
        response = await request_task

    assert response.status_code == 200
    assert QUEUE_WAIT_HEADER not in response.headers


@pytest.mark.asyncio
async def test_concurrency_limit_rejects_when_queue_is_full():
    app = AlwaysBlockingAsgiApp()
    middleware = V1ConcurrencyLimitMiddleware(app, max_inflight=1, max_queue_size=1, queue_timeout_seconds=1)

    async with await _client(middleware) as client:
        first_task = asyncio.create_task(client.get("/v1/test"))
        await app.entered_event.wait()
        second_task = asyncio.create_task(client.get("/v1/test"))
        await _wait_for_queue_size(middleware, 1)
        third_response = await client.get("/v1/test")
        app.release_event.set()
        first_response, second_response = await asyncio.gather(first_task, second_task)

    assert third_response.status_code == 429
    assert third_response.json()["reason"] == "queue_full"
    assert third_response.headers[REJECT_REASON_HEADER] == "queue_full"
    assert third_response.headers[RETRY_AFTER_HEADER] == "1"
    assert first_response.status_code == 200
    assert second_response.status_code == 200


@pytest.mark.asyncio
async def test_concurrency_limit_rejects_when_queue_wait_times_out():
    app = AlwaysBlockingAsgiApp()
    middleware = V1ConcurrencyLimitMiddleware(app, max_inflight=1, max_queue_size=1, queue_timeout_seconds=0.01)

    async with await _client(middleware) as client:
        first_task = asyncio.create_task(client.get("/v1/test"))
        await app.entered_event.wait()
        second_response = await client.get("/v1/test")
        app.release_event.set()
        first_response = await first_task

    assert second_response.status_code == 429
    assert second_response.json()["reason"] == "queue_timeout"
    assert second_response.headers[REJECT_REASON_HEADER] == "queue_timeout"
    assert second_response.headers[RETRY_AFTER_HEADER] == "1"
    assert first_response.status_code == 200


@pytest.mark.asyncio
async def test_concurrency_limit_allows_queued_request_after_slot_is_released():
    app = BlockingAsgiApp()
    middleware = V1ConcurrencyLimitMiddleware(app, max_inflight=1, max_queue_size=1, queue_timeout_seconds=1)

    async with await _client(middleware) as client:
        first_task = asyncio.create_task(client.get("/v1/test"))
        await app.entered_event.wait()
        second_task = asyncio.create_task(client.get("/v1/test"))
        await _wait_for_queue_size(middleware, 1)
        app.release_event.set()
        first_response, second_response = await asyncio.gather(first_task, second_task)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert int(second_response.headers[QUEUE_WAIT_HEADER]) >= 0
    assert app.entered == 2
