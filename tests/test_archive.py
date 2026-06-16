import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from storage.archive import ArchivePayload, ArchiveReader, ArchiveWriter
from storage.models import Base


@pytest.mark.asyncio
async def test_archive_writer_persists_original_and_desensitized_prompt():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    writer = ArchiveWriter(session_factory)
    reader = ArchiveReader(session_factory)

    await writer.write(
        ArchivePayload(
            request_id="req_archive_1",
            model="gpt-test",
            prompt_original=[{"role": "user", "content": "电话 13812345678"}],
            prompt_desensitized=[{"role": "user", "content": "电话 138****5678"}],
            response={"content": "ok"},
            is_desensitized=True,
            action_taken="desensitized",
            matched_rule_ids=["RG-PHONE-CN"],
        )
    )

    archives = await reader.recent()

    assert len(archives) == 1
    assert archives[0].request_id == "req_archive_1"
    assert "13812345678" in archives[0].prompt_original
    assert "138****5678" in archives[0].prompt_desensitized
    assert archives[0].is_desensitized is True
    assert archives[0].action_taken == "desensitized"

    await engine.dispose()
