from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
import json
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import settings
from storage.database import get_session_factory
from storage.models import AuditLog, GeneratedReport, RuntimeSample, TrainingConversation, utc_now

REPORT_TYPES = {"daily", "weekly", "monthly"}
REPORT_STATUSES = {"pending", "running", "succeeded", "failed"}
REPORT_FORMATS = {"pdf", "xlsx", "csv"}
LOCAL_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(slots=True)
class ReportPeriod:
    report_type: str
    start: datetime
    end: datetime
    label: str


@dataclass(slots=True)
class ReportBuildData:
    period: ReportPeriod
    summary: dict
    trend: list[dict]
    rules: list[dict]
    api_keys: list[dict]
    runtime: dict
    high_risk: list[dict]
    include_sensitive: bool


class ReportRepository:
    def __init__(self, session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory or get_session_factory()

    async def list_reports(self, report_type: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[GeneratedReport], int]:
        stmt = select(GeneratedReport)
        count_stmt = select(func.count(GeneratedReport.id))
        if report_type:
            stmt = stmt.where(GeneratedReport.report_type == report_type)
            count_stmt = count_stmt.where(GeneratedReport.report_type == report_type)
        if status:
            stmt = stmt.where(GeneratedReport.status == status)
            count_stmt = count_stmt.where(GeneratedReport.status == status)
        stmt = stmt.order_by(GeneratedReport.period_start.desc(), GeneratedReport.id.desc()).limit(min(max(limit, 1), 100)).offset(max(offset, 0))
        async with self._session_factory() as session:
            total = await session.scalar(count_stmt) or 0
            result = await session.execute(stmt)
            return list(result.scalars().all()), total

    async def get(self, report_id: int) -> GeneratedReport | None:
        async with self._session_factory() as session:
            return await session.get(GeneratedReport, report_id)

    async def create_or_mark_running(self, period: ReportPeriod, mode: str, include_sensitive: bool, generated_by: str) -> GeneratedReport:
        now = utc_now()
        expires_at = now + timedelta(days=max(1, settings.reports_retention_days))
        async with self._session_factory() as session:
            existing = await session.scalar(
                select(GeneratedReport).where(
                    GeneratedReport.report_type == period.report_type,
                    GeneratedReport.period_start == period.start,
                    GeneratedReport.period_end == period.end,
                )
            )
            if existing is None:
                existing = GeneratedReport(report_type=period.report_type, period_start=period.start, period_end=period.end)
                session.add(existing)
            elif existing.status == "running":
                raise ValueError("report is already running")
            existing.timezone = "Asia/Shanghai"
            existing.status = "running"
            existing.generation_mode = mode
            existing.include_sensitive = include_sensitive
            existing.error_message = ""
            existing.generated_by = generated_by
            existing.expires_at = expires_at
            existing.updated_at = now
            await session.commit()
            await session.refresh(existing)
            return existing

    async def mark_succeeded(self, report_id: int, paths: dict[str, str], hashes: dict[str, str], summary: dict, runtime_summary: dict) -> GeneratedReport:
        async with self._session_factory() as session:
            report = await session.get(GeneratedReport, report_id)
            if report is None:
                raise ValueError("report not found")
            report.status = "succeeded"
            report.pdf_path = paths.get("pdf", "")
            report.xlsx_path = paths.get("xlsx", "")
            report.csv_path = paths.get("csv", "")
            report.pdf_sha256 = hashes.get("pdf", "")
            report.xlsx_sha256 = hashes.get("xlsx", "")
            report.csv_sha256 = hashes.get("csv", "")
            report.summary_json = json.dumps(summary, ensure_ascii=False)
            report.runtime_summary_json = json.dumps(runtime_summary, ensure_ascii=False)
            report.generated_at = utc_now()
            report.updated_at = report.generated_at
            await session.commit()
            await session.refresh(report)
            return report

    async def mark_failed(self, report_id: int, error_message: str) -> None:
        async with self._session_factory() as session:
            report = await session.get(GeneratedReport, report_id)
            if report is None:
                return
            report.status = "failed"
            report.error_message = error_message[:2000]
            report.updated_at = utc_now()
            await session.commit()

    async def save_runtime_sample(self, sample: RuntimeSample) -> RuntimeSample:
        async with self._session_factory() as session:
            session.add(sample)
            await session.commit()
            await session.refresh(sample)
            return sample

    async def cleanup_expired(self, now: datetime | None = None) -> int:
        active_now = now or utc_now()
        async with self._session_factory() as session:
            report_result = await session.execute(delete(GeneratedReport).where(GeneratedReport.expires_at.is_not(None), GeneratedReport.expires_at <= active_now))
            sample_cutoff = active_now - timedelta(days=max(1, settings.reports_retention_days))
            await session.execute(delete(RuntimeSample).where(RuntimeSample.sampled_at <= sample_cutoff))
            await session.commit()
            return report_result.rowcount or 0


class ReportAggregator:
    def __init__(self, session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory or get_session_factory()

    async def build_data(self, period: ReportPeriod, include_sensitive: bool = False) -> ReportBuildData:
        async with self._session_factory() as session:
            total_requests = await session.scalar(select(func.count(TrainingConversation.id)).where(TrainingConversation.created_at >= period.start, TrainingConversation.created_at < period.end)) or 0
            action_rows = list((await session.execute(select(AuditLog.action_taken, func.count(AuditLog.id)).where(AuditLog.created_at >= period.start, AuditLog.created_at < period.end).group_by(AuditLog.action_taken))).all())
            rules = list((await session.execute(select(AuditLog.rule_id, AuditLog.rule_level, AuditLog.scanner_type, AuditLog.action_taken, func.count(AuditLog.id).label("count")).where(AuditLog.created_at >= period.start, AuditLog.created_at < period.end).group_by(AuditLog.rule_id, AuditLog.rule_level, AuditLog.scanner_type, AuditLog.action_taken).order_by(func.count(AuditLog.id).desc()).limit(10))).all())
            api_keys = list((await session.execute(select(AuditLog.user_id, func.count(AuditLog.id).label("count")).where(AuditLog.created_at >= period.start, AuditLog.created_at < period.end).group_by(AuditLog.user_id).order_by(func.count(AuditLog.id).desc()).limit(10))).all())
            audit_trend_rows = list((await session.execute(select(AuditLog.created_at, AuditLog.action_taken).where(AuditLog.created_at >= period.start, AuditLog.created_at < period.end))).all())
            high_risk_rows = list((await session.execute(select(AuditLog).where(AuditLog.created_at >= period.start, AuditLog.created_at < period.end, (AuditLog.rule_level == "block") | (AuditLog.action_taken == "blocked")).order_by(AuditLog.created_at.desc()).limit(50))).scalars().all())
            runtime_rows = list((await session.execute(select(RuntimeSample).where(RuntimeSample.sampled_at >= period.start, RuntimeSample.sampled_at < period.end).order_by(RuntimeSample.sampled_at.asc()))).scalars().all())
        actions = {row[0] or "unknown": row[1] for row in action_rows}
        security_events = sum(actions.values())
        summary = {
            "total_requests": total_requests,
            "security_events": security_events,
            "blocked": actions.get("blocked", 0),
            "warn": actions.get("warn", 0),
            "desensitized": actions.get("desensitized", 0),
            "passed": total_requests,
            "event_rate": round(security_events / total_requests * 100, 2) if total_requests else 0,
        }
        return ReportBuildData(
            period=period,
            summary=summary,
            trend=_build_trend(period, audit_trend_rows, runtime_rows),
            rules=[{"rule_id": row[0] or "unknown", "rule_level": row[1] or "", "scanner_type": row[2] or "", "action_taken": row[3] or "", "count": row[4]} for row in rules],
            api_keys=[{"user_id": row[0] or "unknown", "security_events": row[1]} for row in api_keys],
            runtime=_runtime_summary(runtime_rows),
            high_risk=_high_risk_rows(high_risk_rows, include_sensitive),
            include_sensitive=include_sensitive,
        )


def period_for(report_type: str, reference: datetime | None = None) -> ReportPeriod:
    if report_type not in REPORT_TYPES:
        raise ValueError("invalid report_type")
    ref = (reference or datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
    if report_type == "daily":
        day = ref.date() - timedelta(days=1)
        start_local = datetime.combine(day, time.min, tzinfo=LOCAL_TZ)
        end_local = start_local + timedelta(days=1)
        label = day.isoformat()
    elif report_type == "weekly":
        monday = ref.date() - timedelta(days=ref.weekday() + 7)
        start_local = datetime.combine(monday, time.min, tzinfo=LOCAL_TZ)
        end_local = start_local + timedelta(days=7)
        label = f"{monday.isocalendar().year}-W{monday.isocalendar().week:02d}"
    else:
        first_this_month = ref.date().replace(day=1)
        last_month_end = datetime.combine(first_this_month, time.min, tzinfo=LOCAL_TZ)
        year = last_month_end.year if last_month_end.month > 1 else last_month_end.year - 1
        month = last_month_end.month - 1 or 12
        start_local = datetime(year, month, 1, tzinfo=LOCAL_TZ)
        end_local = last_month_end
        label = f"{year}-{month:02d}"
    return ReportPeriod(report_type=report_type, start=start_local.astimezone(UTC), end=end_local.astimezone(UTC), label=label)


def period_from_values(report_type: str, period_value: str) -> ReportPeriod:
    if report_type == "daily":
        start_local = datetime.fromisoformat(period_value).replace(tzinfo=LOCAL_TZ)
        end_local = start_local + timedelta(days=1)
        label = start_local.date().isoformat()
    elif report_type == "weekly":
        year, week = period_value.split("-W", 1)
        start_date = datetime.fromisocalendar(int(year), int(week), 1).date()
        start_local = datetime.combine(start_date, time.min, tzinfo=LOCAL_TZ)
        end_local = start_local + timedelta(days=7)
        label = f"{int(year)}-W{int(week):02d}"
    elif report_type == "monthly":
        year, month = [int(part) for part in period_value.split("-", 1)]
        start_local = datetime(year, month, 1, tzinfo=LOCAL_TZ)
        end_local = datetime(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1, tzinfo=LOCAL_TZ)
        label = f"{year}-{month:02d}"
    else:
        raise ValueError("invalid report_type")
    return ReportPeriod(report_type=report_type, start=start_local.astimezone(UTC), end=end_local.astimezone(UTC), label=label)


def _bucket_label(period: ReportPeriod, value: datetime) -> str:
    local = value.astimezone(LOCAL_TZ)
    if period.report_type == "daily":
        return f"{local.hour:02d}:00"
    return local.date().isoformat()


def _build_trend(period: ReportPeriod, audits: list[tuple[datetime, str | None]], samples: list[RuntimeSample]) -> list[dict]:
    buckets: dict[str, dict] = defaultdict(lambda: {"security_events": 0, "blocked": 0, "cpu_peak": 0.0, "queue_peak": 0, "archive_peak": 0})
    for created_at, action_taken in audits:
        bucket = buckets[_bucket_label(period, created_at)]
        bucket["security_events"] += 1
        if action_taken == "blocked":
            bucket["blocked"] += 1
    for sample in samples:
        bucket = buckets[_bucket_label(period, sample.sampled_at)]
        bucket["cpu_peak"] = max(bucket["cpu_peak"], sample.cpu_percent)
        bucket["queue_peak"] = max(bucket["queue_peak"], sample.v1_queued)
        bucket["archive_peak"] = max(bucket["archive_peak"], sample.archive_queue_size)
    return [{"label": label, **values} for label, values in sorted(buckets.items())]


def _runtime_summary(samples: list[RuntimeSample]) -> dict:
    if not samples:
        return {"sample_count": 0, "series": []}
    cpu_values = [item.cpu_percent for item in samples]
    memory_values = [item.memory_percent for item in samples]
    return {
        "sample_count": len(samples),
        "cpu_avg": round(sum(cpu_values) / len(cpu_values), 2),
        "cpu_peak": round(max(cpu_values), 2),
        "memory_avg": round(sum(memory_values) / len(memory_values), 2),
        "memory_peak": round(max(memory_values), 2),
        "queue_peak": max(item.v1_queued for item in samples),
        "archive_queue_peak": max(item.archive_queue_size for item in samples),
        "data_disk_min_free": min(item.data_disk_free for item in samples),
        "unhealthy_samples": sum(1 for item in samples if item.health_status != "healthy"),
    }


def _high_risk_rows(audits: list[AuditLog], include_sensitive: bool) -> list[dict]:
    rows = [item for item in audits if item.rule_level == "block" or item.action_taken == "blocked"][:50]
    result = []
    for item in rows:
        row = {"id": item.id, "created_at": item.created_at.isoformat(), "user_id": item.user_id, "rule_id": item.rule_id, "rule_level": item.rule_level, "action_taken": item.action_taken}
        if include_sensitive:
            row["matched_snippet"] = item.matched_snippet
            row["desensitized_snippet"] = item.desensitized_snippet
            row["context_snippet"] = item.context_snippet
        result.append(row)
    return result
