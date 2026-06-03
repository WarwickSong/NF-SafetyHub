import json
from typing import Any

from fastapi import APIRouter, Query, Request

from storage.archive import ArchiveReader
from storage.models import MessageArchive

router = APIRouter()


@router.get("/observations/recent")
async def recent_observations(request: Request, limit: int = Query(default=10, ge=1, le=50)):
    reader = getattr(request.app.state, "archive_reader", None) or ArchiveReader()
    archives = await reader.recent(limit)
    return {"items": [_archive_to_observation(archive) for archive in archives]}


def _archive_to_observation(archive: MessageArchive) -> dict[str, Any]:
    return {
        "id": archive.id,
        "request_id": archive.request_id,
        "model": archive.model,
        "capability": archive.capability,
        "action_taken": archive.action_taken,
        "is_stream": archive.is_stream,
        "is_blocked": archive.is_blocked,
        "is_desensitized": archive.is_desensitized,
        "blocked_rule_id": archive.blocked_rule_id,
        "matched_rule_ids": _parse_json(archive.matched_rule_ids, []),
        "messages_original": _parse_json(archive.prompt_original, []),
        "messages_desensitized": _parse_json(archive.prompt_desensitized, []),
        "response": _parse_json(archive.response, archive.response),
        "created_at": archive.created_at.isoformat() if archive.created_at else None,
        "completed_at": archive.completed_at.isoformat() if archive.completed_at else None,
        "latency_ms": archive.latency_ms,
    }


def _parse_json(value: str, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback
