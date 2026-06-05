from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from engine.models import AggregatedScanResult, ScannerResult
from storage.database import get_session_factory
from storage.models import AuditLog


@dataclass(slots=True)
class AuditPayload:
    request_id: str
    scan_result: AggregatedScanResult | ScannerResult
    action_taken: str
    user_id: str = ""
    scanned_text: str = ""


@dataclass(slots=True)
class AuditQuery:
    limit: int = 20
    offset: int = 0
    user_id: str | None = None
    rule_id: str | None = None
    rule_level: str | None = None
    scanner_type: str | None = None
    action_taken: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


@dataclass(slots=True)
class AuditPage:
    items: list[AuditLog]
    total: int
    limit: int
    offset: int


class AuditWriter:
    def __init__(self, session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory or get_session_factory()

    async def write_scan_result(self, payload: AuditPayload) -> list[AuditLog]:
        logs = _logs_from_payload(payload)
        if not logs:
            return []
        async with self._session_factory() as session:
            session.add_all(logs)
            await session.commit()
            for log in logs:
                await session.refresh(log)
            return logs

    async def write_many(self, payloads: list[AuditPayload]) -> None:
        logs = []
        for payload in payloads:
            logs.extend(_logs_from_payload(payload))
        if not logs:
            return
        async with self._session_factory() as session:
            session.add_all(logs)
            await session.commit()


class AuditReader:
    def __init__(self, session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory or get_session_factory()

    async def list(self, query: AuditQuery) -> AuditPage:
        safe_limit = min(max(query.limit, 1), 100)
        safe_offset = max(query.offset, 0)
        stmt = select(AuditLog)
        count_stmt = select(func.count(AuditLog.id))
        for item in _audit_filters(query):
            stmt = stmt.where(item)
            count_stmt = count_stmt.where(item)
        stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(safe_limit).offset(safe_offset)
        async with self._session_factory() as session:
            total = await session.scalar(count_stmt)
            result = await session.execute(stmt)
            return AuditPage(items=list(result.scalars().all()), total=total or 0, limit=safe_limit, offset=safe_offset)

    async def get(self, audit_id: int) -> AuditLog | None:
        async with self._session_factory() as session:
            return await session.get(AuditLog, audit_id)

    async def count_between(self, start_time: datetime, end_time: datetime, rule_level: str | None = None) -> int:
        stmt = select(func.count(AuditLog.id)).where(AuditLog.created_at >= start_time, AuditLog.created_at < end_time)
        if rule_level:
            stmt = stmt.where(AuditLog.rule_level == rule_level)
        async with self._session_factory() as session:
            total = await session.scalar(stmt)
            return total or 0


async def count_audits_between(
    session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession],
    start_time: datetime,
    end_time: datetime,
    rule_level: str | None = None,
) -> int:
    reader = AuditReader(session_factory)
    return await reader.count_between(start_time, end_time, rule_level)


def _logs_from_payload(payload: AuditPayload) -> list[AuditLog]:
    results = _extract_results(payload.scan_result)
    if not results:
        return []
    full_text_hash = _hash_text(payload.scanned_text or _normalized_text(payload.scan_result))
    return [
        AuditLog(
            request_id=payload.request_id,
            user_id=payload.user_id,
            rule_id=result.rule_id,
            rule_name=result.rule_name,
            rule_level=result.level,
            scanner_type=result.scanner_type,
            matched_snippet=result.matched_text,
            full_text_hash=full_text_hash,
            action_taken=payload.action_taken,
        )
        for result in results
        if result.hit
    ]


def _audit_filters(query: AuditQuery) -> list[Any]:
    filters = []
    if query.user_id:
        filters.append(AuditLog.user_id == query.user_id)
    if query.rule_id:
        filters.append(AuditLog.rule_id == query.rule_id)
    if query.rule_level:
        filters.append(AuditLog.rule_level == query.rule_level)
    if query.scanner_type:
        filters.append(AuditLog.scanner_type == query.scanner_type)
    if query.action_taken:
        filters.append(AuditLog.action_taken == query.action_taken)
    if query.start_time:
        filters.append(AuditLog.created_at >= query.start_time)
    if query.end_time:
        filters.append(AuditLog.created_at <= query.end_time)
    return filters


def _extract_results(scan_result: AggregatedScanResult | ScannerResult) -> list[ScannerResult]:
    if isinstance(scan_result, ScannerResult):
        return [scan_result]
    return list(scan_result.results)


def _normalized_text(scan_result: AggregatedScanResult | ScannerResult) -> str:
    if isinstance(scan_result, AggregatedScanResult):
        return scan_result.normalized_text
    return ""


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
