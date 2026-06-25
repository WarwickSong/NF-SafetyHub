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


@pytest.mark.asyncio
async def test_audit_writer_persists_each_scan_hit():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    writer = AuditWriter(session_factory)
    text = "第一个电话 13812345678，第二个电话 13912345678"
    first_start = text.index("13812345678")
    second_start = text.index("13912345678")
    scan_result = AggregatedScanResult(
        results=[
            ScannerResult(
                hit=True,
                rule_id="RG-PHONE-CN",
                rule_name="PII-中国手机号",
                level="desensitize",
                matched_text="13******78",
                position=(first_start, first_start + 11),
                scanner_type="regex",
            ),
            ScannerResult(
                hit=True,
                rule_id="RG-PHONE-CN",
                rule_name="PII-中国手机号",
                level="desensitize",
                matched_text="13******78",
                position=(second_start, second_start + 11),
                scanner_type="regex",
            ),
        ],
        normalized_text=text,
    )

    logs = await writer.write_scan_result(
        AuditPayload(
            request_id="req_audit_multiple_hits",
            scan_result=scan_result,
            action_taken="desensitized",
            scanned_text=text,
            desensitized_text="第一个电话 138****5678，第二个电话 139****5678",
        )
    )

    assert len(logs) == 2
    assert "13812345678" in logs[0].context_snippet
    assert "13912345678" in logs[1].context_snippet
    assert logs[0].request_id == logs[1].request_id == "req_audit_multiple_hits"

    await engine.dispose()


@pytest.mark.asyncio
async def test_audit_context_uses_position_for_original_and_desensitized_text():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    writer = AuditWriter(session_factory)
    prefix = "工具调用输出" * 20
    phone = "23123456727"
    suffix = "后续上下文"
    normalized_text = f"{prefix}{phone}{suffix}"
    scan_result = AggregatedScanResult(
        results=[
            ScannerResult(
                hit=True,
                rule_id="RG-PHONE-INTL",
                rule_name="PII-国际电话",
                level="desensitize",
                matched_text="23******27",
                position=(len(prefix), len(prefix) + len(phone)),
                scanner_type="regex",
            )
        ],
        normalized_text=normalized_text,
    )

    logs = await writer.write_scan_result(
        AuditPayload(
            request_id="req_audit_position",
            scan_result=scan_result,
            action_taken="desensitized",
            scanned_text=normalized_text,
            desensitized_text=f"{prefix}231****6727{suffix}",
        )
    )

    assert len(logs) == 1
    assert "23123456727" in logs[0].context_snippet
    assert "231****6727" in logs[0].desensitized_snippet
    assert suffix in logs[0].context_snippet
    assert suffix in logs[0].desensitized_snippet
    assert logs[0].context_snippet != normalized_text[:160]

    await engine.dispose()
