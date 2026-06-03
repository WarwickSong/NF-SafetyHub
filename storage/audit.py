from collections.abc import Callable
from dataclasses import dataclass
import hashlib

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


class AuditWriter:
    def __init__(self, session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory or get_session_factory()

    async def write_scan_result(self, payload: AuditPayload) -> list[AuditLog]:
        results = _extract_results(payload.scan_result)
        if not results:
            return []
        full_text_hash = _hash_text(payload.scanned_text or _normalized_text(payload.scan_result))
        async with self._session_factory() as session:
            logs = [
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
            if not logs:
                return []
            session.add_all(logs)
            await session.commit()
            for log in logs:
                await session.refresh(log)
            return logs


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
