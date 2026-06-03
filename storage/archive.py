from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from storage.database import get_session_factory
from storage.models import MessageArchive


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
                completed_at=datetime.utcnow(),
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


def _serialize_json(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
