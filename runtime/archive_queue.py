import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal

from config import settings
from storage.archive import ArchivePayload, ArchiveWriter
from storage.audit import AuditPayload, AuditWriter

ArchiveQueueKind = Literal["archive", "audit"]


@dataclass(slots=True)
class ArchiveQueueItem:
    kind: ArchiveQueueKind
    payload: ArchivePayload | AuditPayload


class ArchiveQueue:
    def __init__(
        self,
        archive_writer: ArchiveWriter | None = None,
        audit_writer: AuditWriter | None = None,
        max_size: int | None = None,
        batch_size: int | None = None,
        flush_interval_seconds: float | None = None,
    ):
        self._archive_writer = archive_writer or ArchiveWriter()
        self._audit_writer = audit_writer or AuditWriter()
        self._queue: asyncio.Queue[ArchiveQueueItem] = asyncio.Queue(maxsize=max(1, max_size or settings.archive_queue_max_size))
        self._batch_size = max(1, batch_size or settings.archive_batch_size)
        self._flush_interval_seconds = max(0.01, flush_interval_seconds or settings.archive_flush_interval_seconds)
        self._task: asyncio.Task | None = None
        self._dropped = 0
        self._processed = 0
        self._running = False

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        await self._queue.join()
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task

    def enqueue_archive(self, payload: ArchivePayload) -> bool:
        return self._enqueue(ArchiveQueueItem("archive", payload))

    def enqueue_audit(self, payload: AuditPayload) -> bool:
        return self._enqueue(ArchiveQueueItem("audit", payload))

    def snapshot(self) -> dict[str, int]:
        return {
            "queue_size": self._queue.qsize(),
            "max_size": self._queue.maxsize,
            "dropped": self._dropped,
            "processed": self._processed,
        }

    def _enqueue(self, item: ArchiveQueueItem) -> bool:
        try:
            self._queue.put_nowait(item)
            return True
        except asyncio.QueueFull:
            self._dropped += 1
            return False

    async def _run(self) -> None:
        while self._running or not self._queue.empty():
            batch = await self._next_batch()
            archive_payloads = [item.payload for item in batch if item.kind == "archive"]
            audit_payloads = [item.payload for item in batch if item.kind == "audit"]
            try:
                if archive_payloads:
                    await self._archive_writer.write_many(archive_payloads)
                    self._processed += len(archive_payloads)
                if audit_payloads:
                    await self._audit_writer.write_many(audit_payloads)
                    self._processed += len(audit_payloads)
            except Exception:
                pass
            finally:
                for _ in batch:
                    self._queue.task_done()

    async def _next_batch(self) -> list[ArchiveQueueItem]:
        first = await self._queue.get()
        batch = [first]
        deadline = asyncio.get_running_loop().time() + self._flush_interval_seconds
        while len(batch) < self._batch_size:
            timeout = max(0, deadline - asyncio.get_running_loop().time())
            if timeout <= 0:
                break
            try:
                batch.append(await asyncio.wait_for(self._queue.get(), timeout=timeout))
            except TimeoutError:
                break
        return batch
