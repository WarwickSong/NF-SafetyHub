from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from storage.database import get_session_factory
from storage.models import MessageArchive, utc_now


@dataclass(slots=True)
class ArchivePayload:
    request_id: str
    model: str = ""
    capability: str = "chat"
    prompt_original: Any = None
    prompt_desensitized: Any = None
    response: Any = None
    is_stream: bool = False
    is_blocked: bool = False
    is_desensitized: bool = False
    action_taken: str = "passed"
    blocked_rule_id: str = ""
    matched_rule_ids: list[str] | None = None
    user_id: str = ""
    api_key_id: str = ""
    approval_id: str = ""
    file_ids: list[str] | None = None
    image_metadata: Any = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0


@dataclass(slots=True)
class ArchiveQuery:
    limit: int = 20
    offset: int = 0
    user_id: str | None = None
    model: str | None = None
    action_taken: str | None = None
    is_blocked: bool | None = None
    keyword: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


@dataclass(slots=True)
class ArchivePage:
    items: list[MessageArchive]
    total: int
    limit: int
    offset: int


@dataclass(slots=True)
class ArchiveStats:
    total: int
    blocked: int
    desensitized: int
    passed: int
    by_action: dict[str, int]
    by_model: dict[str, int]


class ArchiveWriter:
    def __init__(self, session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory or get_session_factory()

    async def write(self, payload: ArchivePayload) -> MessageArchive:
        async with self._session_factory() as session:
            archive = MessageArchive(
                request_id=payload.request_id,
                user_id=payload.user_id,
                api_key_id=payload.api_key_id,
                model=payload.model,
                capability=payload.capability,
                prompt=_serialize_json(payload.prompt_desensitized if payload.prompt_desensitized is not None else payload.prompt_original),
                prompt_original=_serialize_json(payload.prompt_original),
                prompt_desensitized=_serialize_json(payload.prompt_desensitized if payload.prompt_desensitized is not None else payload.prompt_original),
                response=_serialize_json(payload.response),
                is_stream=payload.is_stream,
                is_blocked=payload.is_blocked,
                is_desensitized=payload.is_desensitized,
                action_taken=payload.action_taken,
                blocked_rule_id=payload.blocked_rule_id,
                matched_rule_ids=_serialize_json(payload.matched_rule_ids or []),
                approval_id=payload.approval_id,
                file_ids=_serialize_json(payload.file_ids or []),
                image_metadata=_serialize_json(payload.image_metadata or {}),
                prompt_tokens=payload.prompt_tokens,
                completion_tokens=payload.completion_tokens,
                completed_at=utc_now(),
                latency_ms=payload.latency_ms,
            )
            session.add(archive)
            await session.commit()
            await session.refresh(archive)
            return archive


class ArchiveReader:
    def __init__(self, session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory or get_session_factory()

    async def recent(self, limit: int = 10) -> list[MessageArchive]:
        safe_limit = min(max(limit, 1), 50)
        async with self._session_factory() as session:
            result = await session.execute(
                select(MessageArchive)
                .order_by(MessageArchive.created_at.desc(), MessageArchive.id.desc())
                .limit(safe_limit)
            )
            return list(result.scalars().all())

    async def list(self, query: ArchiveQuery) -> ArchivePage:
        safe_limit = min(max(query.limit, 1), 100)
        safe_offset = max(query.offset, 0)
        stmt = select(MessageArchive)
        count_stmt = select(func.count(MessageArchive.id))
        for item in _archive_filters(query):
            stmt = stmt.where(item)
            count_stmt = count_stmt.where(item)
        stmt = stmt.order_by(MessageArchive.created_at.desc(), MessageArchive.id.desc()).limit(safe_limit).offset(safe_offset)
        async with self._session_factory() as session:
            total = await session.scalar(count_stmt)
            result = await session.execute(stmt)
            return ArchivePage(items=list(result.scalars().all()), total=total or 0, limit=safe_limit, offset=safe_offset)

    async def get(self, archive_id: int) -> MessageArchive | None:
        async with self._session_factory() as session:
            return await session.get(MessageArchive, archive_id)

    async def stats(self, query: ArchiveQuery | None = None) -> ArchiveStats:
        active_query = query or ArchiveQuery()
        base_stmt = select(MessageArchive)
        for item in _archive_filters(active_query):
            base_stmt = base_stmt.where(item)
        subquery = base_stmt.subquery()
        async with self._session_factory() as session:
            total = await session.scalar(select(func.count()).select_from(subquery)) or 0
            blocked = await session.scalar(select(func.count()).select_from(subquery).where(subquery.c.is_blocked.is_(True))) or 0
            desensitized = await session.scalar(select(func.count()).select_from(subquery).where(subquery.c.is_desensitized.is_(True))) or 0
            passed = await session.scalar(select(func.count()).select_from(subquery).where(subquery.c.action_taken == "passed")) or 0
            action_rows = await session.execute(select(subquery.c.action_taken, func.count()).group_by(subquery.c.action_taken))
            model_rows = await session.execute(select(subquery.c.model, func.count()).group_by(subquery.c.model))
            return ArchiveStats(
                total=total,
                blocked=blocked,
                desensitized=desensitized,
                passed=passed,
                by_action={key or "unknown": value for key, value in action_rows.all()},
                by_model={key or "unknown": value for key, value in model_rows.all()},
            )


async def count_archives_between(
    session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession],
    start_time: datetime,
    end_time: datetime,
) -> int:
    async with session_factory() as session:
        total = await session.scalar(
            select(func.count(MessageArchive.id)).where(
                MessageArchive.created_at >= start_time,
                MessageArchive.created_at < end_time,
            )
        )
        return total or 0


def _archive_filters(query: ArchiveQuery) -> list[Any]:
    filters = []
    if query.user_id:
        filters.append(MessageArchive.user_id == query.user_id)
    if query.model:
        filters.append(MessageArchive.model == query.model)
    if query.action_taken:
        filters.append(MessageArchive.action_taken == query.action_taken)
    if query.is_blocked is not None:
        filters.append(MessageArchive.is_blocked.is_(query.is_blocked))
    if query.keyword:
        pattern = f"%{query.keyword}%"
        filters.append(
            or_(
                MessageArchive.prompt_original.like(pattern),
                MessageArchive.prompt_desensitized.like(pattern),
                MessageArchive.response.like(pattern),
            )
        )
    if query.start_time:
        filters.append(MessageArchive.created_at >= query.start_time)
    if query.end_time:
        filters.append(MessageArchive.created_at <= query.end_time)
    return filters


def _serialize_json(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
