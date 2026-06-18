from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import settings
from storage.archive import ArchivePayload
from storage.database import get_session_factory
from storage.models import TrainingConversation, utc_now


@dataclass(slots=True)
class TrainingSummary:
    total: int
    covered: int
    pending_analysis: int
    active: int
    expired: int


@dataclass(slots=True)
class TrainingCleanupPreview:
    covered: int
    expired: int


@dataclass(slots=True)
class TrainingCleanupResult:
    covered_deleted: int = 0
    expired_deleted: int = 0


class TrainingConversationWriter:
    def __init__(self, session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory or get_session_factory()

    async def write_from_archive_payload(self, payload: ArchivePayload) -> TrainingConversation | None:
        conversations = await self.write_many_from_archive_payloads([payload])
        return conversations[0] if conversations else None

    async def write_many_from_archive_payloads(self, payloads: list[ArchivePayload]) -> list[TrainingConversation]:
        conversations = [_conversation_from_payload(payload) for payload in payloads]
        conversations = [conversation for conversation in conversations if conversation is not None]
        if not conversations:
            return []
        async with self._session_factory() as session:
            session.add_all(conversations)
            await session.commit()
            for conversation in conversations:
                await session.refresh(conversation)
            return conversations


class TrainingConversationReader:
    def __init__(self, session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory or get_session_factory()

    async def summary(self) -> TrainingSummary:
        now = utc_now()
        async with self._session_factory() as session:
            total = await session.scalar(select(func.count(TrainingConversation.id))) or 0
            covered = await session.scalar(select(func.count(TrainingConversation.id)).where(TrainingConversation.covered_by_conversation_id != "")) or 0
            pending = await session.scalar(select(func.count(TrainingConversation.id)).where(TrainingConversation.analysis_status == "pending")) or 0
            expired = await session.scalar(select(func.count(TrainingConversation.id)).where(TrainingConversation.expires_at.is_not(None), TrainingConversation.expires_at <= now)) or 0
        return TrainingSummary(total=total, covered=covered, pending_analysis=pending, active=max(total - covered, 0), expired=expired)

    async def preview_cleanup(self, include_covered: bool = True, include_expired: bool = True, limit: int = 1000) -> TrainingCleanupPreview:
        safe_limit = _safe_limit(limit)
        async with self._session_factory() as session:
            covered_ids = await _select_ids(session, _covered_stmt(safe_limit)) if include_covered else []
            expired_ids = await _select_ids(session, _expired_stmt(safe_limit)) if include_expired else []
        return TrainingCleanupPreview(covered=len(covered_ids), expired=len(expired_ids))

    async def cleanup(self, include_covered: bool = True, include_expired: bool = True, limit: int = 1000) -> TrainingCleanupResult:
        safe_limit = _safe_limit(limit)
        result = TrainingCleanupResult()
        async with self._session_factory() as session:
            covered_ids = await _select_ids(session, _covered_stmt(safe_limit)) if include_covered else []
            expired_ids = await _select_ids(session, _expired_stmt(safe_limit)) if include_expired else []
            if covered_ids:
                await session.execute(delete(TrainingConversation).where(TrainingConversation.id.in_(covered_ids)))
                result.covered_deleted = len(covered_ids)
            if expired_ids:
                await session.execute(delete(TrainingConversation).where(TrainingConversation.id.in_(expired_ids)))
                result.expired_deleted = len(expired_ids)
            await session.commit()
        return result


def _conversation_from_payload(payload: ArchivePayload) -> TrainingConversation | None:
    if not _is_training_candidate(payload):
        return None
    messages = _normalize_messages(payload.prompt_desensitized if payload.prompt_desensitized is not None else payload.prompt_original)
    assistant_response = _extract_assistant_response(payload.response)
    if not messages or not assistant_response:
        return None
    trajectory = _append_assistant_message(messages, assistant_response)
    serialized_messages = _serialize_json(messages)
    serialized_trajectory = _serialize_json(trajectory)
    now = utc_now()
    return TrainingConversation(
        conversation_id=uuid4().hex,
        request_id=payload.request_id,
        user_id=payload.user_id,
        api_key_id=payload.api_key_id,
        model=payload.model,
        capability=payload.capability,
        messages=serialized_messages,
        assistant_response=assistant_response,
        trajectory=serialized_trajectory,
        trajectory_hash=_hash_text(serialized_trajectory),
        prompt_bytes=len(serialized_messages.encode("utf-8")),
        response_bytes=len(assistant_response.encode("utf-8")),
        is_desensitized=payload.is_desensitized,
        expires_at=now + timedelta(days=settings.archive_retention_days) if settings.archive_retention_days > 0 else None,
        created_at=now,
    )


def _is_training_candidate(payload: ArchivePayload) -> bool:
    return payload.capability == "chat" and payload.action_taken == "passed" and not payload.is_blocked


def _extract_assistant_response(response: Any) -> str:
    response_obj = response
    if isinstance(response, str):
        response_obj = _loads_json(response)
    if not isinstance(response_obj, dict):
        return ""
    if response_obj.get("truncated"):
        return ""
    if response_obj.get("message_content"):
        return _normalize_text(str(response_obj.get("message_content") or ""))
    content = response_obj.get("content")
    content_obj = _loads_json(content) if isinstance(content, str) else content
    if not isinstance(content_obj, dict):
        return ""
    choices = content_obj.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""
    return _normalize_text(str(message.get("content") or ""))


def _normalize_messages(value: Any) -> list[dict[str, Any]]:
    messages = value if isinstance(value, list) else _loads_json(value)
    if not isinstance(messages, list):
        return []
    normalized: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "")).strip()
        content = _normalize_content(message.get("content"))
        if role:
            normalized.append({"role": role, "content": content})
    return normalized


def _append_assistant_message(messages: list[dict[str, Any]], response_text: str) -> list[dict[str, Any]]:
    return [*messages, {"role": "assistant", "content": response_text}]


def _normalize_content(content: Any) -> Any:
    if isinstance(content, str):
        return _normalize_text(content)
    if isinstance(content, list):
        return [_normalize_content(item) for item in content]
    if isinstance(content, dict):
        return {key: _normalize_content(content[key]) for key in sorted(content)}
    return content


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _loads_json(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _serialize_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def _covered_stmt(limit: int):
    return select(TrainingConversation.id).where(TrainingConversation.covered_by_conversation_id != "").order_by(TrainingConversation.created_at.asc()).limit(limit)


def _expired_stmt(limit: int):
    now = utc_now()
    return select(TrainingConversation.id).where(TrainingConversation.expires_at.is_not(None), TrainingConversation.expires_at <= now).order_by(TrainingConversation.expires_at.asc()).limit(limit)


async def _select_ids(session: AsyncSession, stmt) -> list[int]:
    rows = await session.execute(stmt)
    return [int(item) for item in rows.scalars().all()]


def _safe_limit(limit: int) -> int:
    return min(max(limit, 1), 10000)
