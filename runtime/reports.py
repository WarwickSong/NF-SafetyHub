from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, time, timedelta
import fcntl
import json
import os
from pathlib import Path
import shutil
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import httpx
import psutil

from config import settings
from middleware.concurrency_limit import get_v1_concurrency_snapshot
from reports.generator import generate_report_files, resolve_report_path
from storage.models import RuntimeSample, utc_now
from storage.reports import LOCAL_TZ, ReportAggregator, ReportPeriod, ReportRepository, period_for


class ReportService:
    def __init__(self, session_factory=None, archive_queue=None):
        self._repository = ReportRepository(session_factory)
        self._aggregator = ReportAggregator(session_factory)
        self._archive_queue = archive_queue
        self._generation_lock = asyncio.Lock()

    async def list_reports(self, report_type: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0):
        return await self._repository.list_reports(report_type=report_type, status=status, limit=limit, offset=offset)

    async def get_report(self, report_id: int):
        return await self._repository.get(report_id)

    async def generate(self, period: ReportPeriod, mode: str = "manual", include_sensitive: bool = False, generated_by: str = "system"):
        async with self._generation_lock:
            lock_name = f"generate_{period.report_type}_{period.label}"
            with _file_lock(lock_name):
                report = await self._repository.create_or_mark_running(period, mode, include_sensitive, generated_by)
                try:
                    data = await self._aggregator.build_data(period, include_sensitive=include_sensitive)
                    paths, hashes = await asyncio.to_thread(generate_report_files, data, report.id)
                    return await self._repository.mark_succeeded(report.id, paths, hashes, data.summary, data.runtime)
                except Exception as exc:
                    await self._repository.mark_failed(report.id, str(exc))
                    raise

    async def generate_scheduled(self, report_type: str) -> None:
        try:
            period = period_for(report_type)
            await self.generate(period, mode="scheduled", include_sensitive=False, generated_by="system")
        except RuntimeError:
            return
        except Exception as exc:
            await _send_report_alert(report_type, str(exc))
            return

    async def sample_runtime(self) -> RuntimeSample | None:
        try:
            with _file_lock("runtime_sample"):
                sample = _runtime_sample(self._archive_queue)
                return await self._repository.save_runtime_sample(sample)
        except RuntimeError:
            return None

    async def cleanup_expired(self) -> int:
        with _file_lock("cleanup"):
            removed = await self._repository.cleanup_expired()
            with suppress(Exception):
                _cleanup_expired_files(settings.reports_dir, settings.reports_retention_days)
            return removed

    def resolve_file(self, relative_path: str) -> Path:
        return resolve_report_path(relative_path)


class ReportScheduler:
    def __init__(self, service: ReportService):
        self._service = service
        self._scheduler = AsyncIOScheduler(timezone=str(LOCAL_TZ))

    def start(self) -> None:
        if not settings.reports_enabled or self._scheduler.running:
            return
        interval = max(1, settings.reports_runtime_sample_interval_minutes)
        self._scheduler.add_job(self._service.sample_runtime, "interval", minutes=interval, id="runtime_sample", max_instances=1, coalesce=True)
        self._add_daily_job("daily_report", settings.reports_daily_generate_time, self._service.generate_scheduled, "daily")
        self._add_daily_job("weekly_report", settings.reports_weekly_generate_time, self._service.generate_scheduled, "weekly", day_of_week="mon")
        self._add_daily_job("monthly_report", settings.reports_monthly_generate_time, self._service.generate_scheduled, "monthly", day="1")
        self._add_daily_job("reports_cleanup", "05:00", self._service.cleanup_expired)
        self._scheduler.start()

    async def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def _add_daily_job(self, job_id: str, value: str, func, *args, day_of_week: str | None = None, day: str | None = None) -> None:
        hour, minute = _parse_time(value)
        kwargs: dict[str, Any] = {"hour": hour, "minute": minute, "id": job_id, "max_instances": 1, "coalesce": True}
        if day_of_week:
            kwargs["day_of_week"] = day_of_week
        if day:
            kwargs["day"] = day
        self._scheduler.add_job(func, "cron", args=args, **kwargs)


def _runtime_sample(archive_queue) -> RuntimeSample:
    now = utc_now()
    process = psutil.Process(os.getpid())
    with suppress(Exception):
        process.cpu_percent(None)
    cpu_percent = psutil.cpu_percent(interval=None)
    memory_percent = psutil.virtual_memory().percent
    data_disk = _disk_usage(settings.data_disk_monitor_path)
    system_disk = _disk_usage(settings.system_disk_monitor_container_path)
    v1 = get_v1_concurrency_snapshot() or {}
    archive = archive_queue.snapshot() if archive_queue is not None else {}
    raw = {
        "process_memory_rss": getattr(process.memory_info(), "rss", 0),
        "v1": v1,
        "archive": archive,
    }
    return RuntimeSample(
        sampled_at=now,
        worker_pid=os.getpid(),
        health_status="healthy",
        cpu_percent=round(cpu_percent, 2),
        memory_percent=round(memory_percent, 2),
        data_disk_total=data_disk[0],
        data_disk_used=data_disk[1],
        data_disk_free=data_disk[2],
        system_disk_total=system_disk[0],
        system_disk_used=system_disk[1],
        system_disk_free=system_disk[2],
        v1_inflight=int(v1.get("inflight") or 0),
        v1_queued=int(v1.get("queue_size") or 0),
        archive_queue_size=int(archive.get("queue_size") or 0),
        archive_processed_total=int(archive.get("processed") or 0),
        archive_dropped_total=int(archive.get("dropped") or 0),
        raw_json=json.dumps(raw, ensure_ascii=False),
    )


def _disk_usage(path: Path) -> tuple[int, int, int]:
    try:
        usage = shutil.disk_usage(path)
        return usage.total, usage.used, usage.free
    except OSError:
        return 0, 0, 0


def _parse_time(value: str) -> tuple[int, int]:
    parsed = time.fromisoformat(value)
    return parsed.hour, parsed.minute


def _cleanup_expired_files(root: Path, retention_days: int) -> None:
    if not root.exists():
        return
    cutoff = datetime.now().timestamp() - max(1, retention_days) * 86400
    for path in root.rglob("*"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)


class _file_lock:
    def __init__(self, name: str):
        self.path = settings.reports_dir / ".locks" / f"{name}.lock"
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("w")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise RuntimeError("report task is already running") from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


async def _send_report_alert(report_type: str, error_message: str) -> None:
    if not settings.webhook_url:
        return
    payload = _alert_payload(report_type, error_message)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(settings.webhook_url, json=payload)
    except Exception:
        return


def _alert_payload(report_type: str, error_message: str) -> dict[str, Any]:
    title = f"SafetyHub {report_type} 报表生成失败"
    message = f"{title}\n错误摘要：{error_message[:500]}"
    if settings.webhook_type == "dingtalk":
        return {"msgtype": "text", "text": {"content": message}}
    return {"msgtype": "text", "text": {"content": message}}
