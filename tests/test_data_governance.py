import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from storage.data_governance import CoverageAnalysisConfig, DataGovernanceService
from storage.models import Base, TrainingConversation


@pytest.mark.asyncio
async def test_coverage_analysis_keeps_longest_trajectories_by_user_and_key():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    short = _conversation("short", "user-a", "key-a", "model-a", [_message("user", "问题一"), _message("assistant", "回答一")])
    medium = _conversation("medium", "user-a", "key-a", "model-b", [*_trajectory(short), _message("user", "问题二"), _message("assistant", "回答二")])
    longest = _conversation("longest", "user-a", "key-a", "model-c", [*_trajectory(medium), _message("user", "问题三"), _message("assistant", "回答三")])
    other_user = _conversation("other-user", "user-b", "key-a", "model-c", _trajectory(short))
    other_key = _conversation("other-key", "user-a", "key-b", "model-c", _trajectory(short))

    async with session_factory() as session:
        session.add_all([short, medium, longest, other_user, other_key])
        await session.commit()

    result = await DataGovernanceService(session_factory).run_coverage_analysis(
        config=CoverageAnalysisConfig(max_seconds=60, max_records=10, batch_size=10, batch_sleep_ms=0)
    )

    async with session_factory() as session:
        records = {record.conversation_id: record for record in (await session.execute(select(TrainingConversation))).scalars().all()}

    assert result.status == "completed"
    assert result.processed_count == 5
    assert result.marked_count == 2
    assert records["short"].covered_by_conversation_id == "longest"
    assert records["medium"].covered_by_conversation_id == "longest"
    assert records["longest"].covered_by_conversation_id == ""
    assert records["other-user"].covered_by_conversation_id == ""
    assert records["other-key"].covered_by_conversation_id == ""

    await engine.dispose()


def _conversation(conversation_id: str, user_id: str, api_key_id: str, model: str, trajectory: list[dict[str, str]]) -> TrainingConversation:
    return TrainingConversation(
        conversation_id=conversation_id,
        user_id=user_id,
        api_key_id=api_key_id,
        model=model,
        trajectory=json.dumps(trajectory, ensure_ascii=False, separators=(",", ":")),
    )


def _trajectory(conversation: TrainingConversation) -> list[dict[str, str]]:
    return json.loads(conversation.trajectory)


def _message(role: str, content: str) -> dict[str, str]:
    return {"role": role, "content": content}
