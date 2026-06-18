from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import timedelta
import asyncio
import json
from time import monotonic
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import settings
from storage.database import get_session_factory
from storage.models import AuditLog, DataGovernanceJob, TrainingConversation, utc_now
from storage.training import TrainingCleanupPreview, TrainingCleanupResult, TrainingConversationReader


@dataclass(slots=True)
class DataGovernanceSummary:
    training_total: int
    training_active: int
    training_covered: int
    training_pending_analysis: int
    training_expired: int
    audit_total: int
    audit_expired: int
    running_job: dict[str, Any] | None


@dataclass(slots=True)
class DataGovernanceCleanupPreview:
    training: TrainingCleanupPreview
    audit_expired: int


@dataclass(slots=True)
class DataGovernanceCleanupResult:
    training: TrainingCleanupResult
    audit_deleted: int = 0


@dataclass(slots=True)
class CoverageAnalysisResult:
    job_id: int
    status: str
    processed_count: int
    marked_count: int
    cursor_value: str
    error: str = ""


@dataclass(slots=True)
class CoverageAnalysisConfig:
    max_seconds: int = settings.data_governance_coverage_max_seconds
    max_records: int = settings.data_governance_coverage_max_records
    batch_size: int = settings.data_governance_coverage_batch_size
    batch_sleep_ms: int = settings.data_governance_coverage_batch_sleep_ms


class DataGovernanceService:
    def __init__(self, session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory or get_session_factory()
        self._training_reader = TrainingConversationReader(self._session_factory)

    async def summary(self) -> DataGovernanceSummary:
        now = utc_now()
        training = await self._training_reader.summary()
        async with self._session_factory() as session:
            audit_total = await session.scalar(select(func.count(AuditLog.id))) or 0
            audit_expired = await session.scalar(select(func.count(AuditLog.id)).where(AuditLog.created_at <= _audit_cutoff(now))) or 0
            running_job = await _running_job(session)
        return DataGovernanceSummary(
            training_total=training.total,
            training_active=training.active,
            training_covered=training.covered,
            training_pending_analysis=training.pending_analysis,
            training_expired=training.expired,
            audit_total=audit_total,
            audit_expired=audit_expired,
            running_job=_job_to_dict(running_job) if running_job else None,
        )

    async def coverage_status(self) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            job = await _running_job(session)
            if job is None:
                row = await session.execute(select(DataGovernanceJob).order_by(DataGovernanceJob.started_at.desc(), DataGovernanceJob.id.desc()).limit(1))
                job = row.scalars().first()
            return _job_to_dict(job) if job else None

    async def run_coverage_analysis(self, requested_by: str = "", config: CoverageAnalysisConfig | None = None) -> CoverageAnalysisResult:
        active_config = config or CoverageAnalysisConfig()
        async with self._session_factory() as session:
            existing = await _running_job(session)
            if existing is not None:
                return CoverageAnalysisResult(existing.id, existing.status, existing.processed_count, existing.marked_count, existing.cursor_value, "coverage analysis already running")
            job = DataGovernanceJob(
                job_type="coverage_analysis",
                status="running",
                requested_by=requested_by,
                config_snapshot=json.dumps(asdict(active_config), ensure_ascii=False, separators=(",", ":")),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
        return await self._execute_coverage_job(job.id, active_config)

    async def preview_cleanup(self, include_training_covered: bool = True, include_training_expired: bool = True, include_audit_expired: bool = True, limit: int = 1000) -> DataGovernanceCleanupPreview:
        training_preview = await self._training_reader.preview_cleanup(include_training_covered, include_training_expired, limit)
        audit_expired = 0
        if include_audit_expired:
            async with self._session_factory() as session:
                audit_ids = await _select_ids(session, _expired_audit_stmt(limit))
                audit_expired = len(audit_ids)
        return DataGovernanceCleanupPreview(training=training_preview, audit_expired=audit_expired)

    async def cleanup(self, include_training_covered: bool = False, include_training_expired: bool = True, include_audit_expired: bool = True, limit: int = 1000) -> DataGovernanceCleanupResult:
        training_result = await self._training_reader.cleanup(include_training_covered, include_training_expired, limit)
        audit_deleted = 0
        if include_audit_expired:
            async with self._session_factory() as session:
                audit_ids = await _select_ids(session, _expired_audit_stmt(limit))
                if audit_ids:
                    await session.execute(delete(AuditLog).where(AuditLog.id.in_(audit_ids)))
                    await session.commit()
                    audit_deleted = len(audit_ids)
        return DataGovernanceCleanupResult(training=training_result, audit_deleted=audit_deleted)

    async def _execute_coverage_job(self, job_id: int, config: CoverageAnalysisConfig) -> CoverageAnalysisResult:
        started = monotonic()
        processed = 0
        marked = 0
        cursor = 0
        error = ""
        status = "completed"
        try:
            while processed < config.max_records and monotonic() - started < config.max_seconds:
                batch_limit = min(max(config.batch_size, 1), config.max_records - processed)
                async with self._session_factory() as session:
                    job = await session.get(DataGovernanceJob, job_id)
                    if job is None or job.status == "stopping":
                        status = "stopped"
                        break
                    rows = await session.execute(
                        select(TrainingConversation)
                        .where(TrainingConversation.analysis_status == "pending")
                        .where(TrainingConversation.id > cursor)
                        .order_by(TrainingConversation.id.asc())
                        .limit(batch_limit)
                    )
                    conversations = list(rows.scalars().all())
                    if not conversations:
                        break
                    for conversation in conversations:
                        cursor = conversation.id
                        processed += 1
                    marked += await _mark_covered_by_group(session, conversations)
                    for conversation in conversations:
                        conversation.analysis_status = "analyzed"
                        conversation.analyzed_at = utc_now()
                    job.processed_count = processed
                    job.marked_count = marked
                    job.cursor_value = str(cursor)
                    job.updated_at = utc_now()
                    await session.commit()
                if config.batch_sleep_ms > 0:
                    await asyncio.sleep(config.batch_sleep_ms / 1000)
            if processed >= config.max_records:
                status = "limited"
            elif monotonic() - started >= config.max_seconds:
                status = "timeout"
        except Exception as exc:
            status = "failed"
            error = str(exc)
        async with self._session_factory() as session:
            job = await session.get(DataGovernanceJob, job_id)
            if job is not None:
                job.status = status
                job.processed_count = processed
                job.marked_count = marked
                job.cursor_value = str(cursor)
                job.error = error
                job.finished_at = utc_now()
                job.updated_at = utc_now()
                await session.commit()
        return CoverageAnalysisResult(job_id, status, processed, marked, str(cursor), error)


async def _mark_covered_by_group(session: AsyncSession, conversations: list[TrainingConversation]) -> int:
    marked = 0
    groups: dict[tuple[str, str], list[TrainingConversation]] = {}
    for conversation in conversations:
        groups.setdefault((conversation.user_id, conversation.api_key_id), []).append(conversation)
    for group_conversations in groups.values():
        covered_ids = {conversation.id for conversation in group_conversations if conversation.covered_by_conversation_id}
        for conversation in sorted(group_conversations, key=lambda item: item.id, reverse=True):
            if conversation.id in covered_ids:
                continue
            trajectory = _parse_trajectory(conversation.trajectory)
            if len(trajectory) < 2:
                continue
            candidates = await _candidate_conversations(session, conversation)
            for candidate in candidates:
                if candidate.id in covered_ids or candidate.covered_by_conversation_id:
                    covered_ids.add(candidate.id)
                    continue
                candidate_trajectory = _parse_trajectory(candidate.trajectory)
                if _is_prefix_trajectory(candidate_trajectory, trajectory):
                    candidate.covered_by_conversation_id = conversation.conversation_id
                    covered_ids.add(candidate.id)
                    marked += 1
    return marked


async def _candidate_conversations(session: AsyncSession, conversation: TrainingConversation) -> list[TrainingConversation]:
    rows = await session.execute(
        select(TrainingConversation)
        .where(TrainingConversation.id != conversation.id)
        .where(TrainingConversation.covered_by_conversation_id == "")
        .where(TrainingConversation.user_id == conversation.user_id)
        .where(TrainingConversation.api_key_id == conversation.api_key_id)
        .where(TrainingConversation.id < conversation.id)
        .order_by(TrainingConversation.id.desc())
    )
    return list(rows.scalars().all())


def _is_prefix_trajectory(candidate_trajectory: list[dict[str, Any]], trajectory: list[dict[str, Any]]) -> bool:
    return bool(candidate_trajectory) and len(candidate_trajectory) < len(trajectory) and trajectory[: len(candidate_trajectory)] == candidate_trajectory


def _parse_trajectory(value: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(value) if value else []
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _audit_cutoff(now):
    if settings.audit_retention_days <= 0:
        return now - timedelta(days=36500)
    return now - timedelta(days=settings.audit_retention_days)


def _expired_audit_stmt(limit: int):
    return select(AuditLog.id).where(AuditLog.created_at <= _audit_cutoff(utc_now())).order_by(AuditLog.created_at.asc()).limit(min(max(limit, 1), 10000))


async def _running_job(session: AsyncSession) -> DataGovernanceJob | None:
    row = await session.execute(
        select(DataGovernanceJob)
        .where(DataGovernanceJob.status.in_(["running", "stopping"]))
        .order_by(DataGovernanceJob.started_at.desc(), DataGovernanceJob.id.desc())
        .limit(1)
    )
    return row.scalars().first()


def _job_to_dict(job: DataGovernanceJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "requested_by": job.requested_by,
        "processed_count": job.processed_count,
        "marked_count": job.marked_count,
        "deleted_count": job.deleted_count,
        "cursor_value": job.cursor_value,
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


async def _select_ids(session: AsyncSession, stmt) -> list[int]:
    rows = await session.execute(stmt)
    return [int(item) for item in rows.scalars().all()]
