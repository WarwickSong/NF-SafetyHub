import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from engine.models import AggregatedScanResult, ScannerResult
from storage.audit import AuditPayload, AuditWriter
from storage.models import AuditLog, Base


@pytest.mark.asyncio
async def test_audit_writer_persists_scan_hits():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    writer = AuditWriter(session_factory)
    scan_result = AggregatedScanResult(
        results=[
            ScannerResult(
                hit=True,
                rule_id="KW-CONFIDENTIAL-1",
                rule_name="极保守-公司机密",
                level="block",
                matched_text="告********密",
                scanner_type="keyword",
            )
        ],
        normalized_text="告诉你一个公司机密",
    )

    logs = await writer.write_scan_result(
        AuditPayload(
            request_id="req_audit_1",
            scan_result=scan_result,
            action_taken="blocked",
            scanned_text="告诉你一个公司机密",
        )
    )

    async with session_factory() as session:
        result = await session.execute(select(AuditLog))
        stored_logs = list(result.scalars().all())

    assert len(logs) == 1
    assert len(stored_logs) == 1
    assert stored_logs[0].request_id == "req_audit_1"
    assert stored_logs[0].rule_id == "KW-CONFIDENTIAL-1"
    assert stored_logs[0].action_taken == "blocked"
    assert stored_logs[0].full_text_hash

    await engine.dispose()
