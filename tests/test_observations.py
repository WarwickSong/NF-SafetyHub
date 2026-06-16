import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import Settings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from admin.router import router
from storage.archive import ArchivePayload, ArchiveReader, ArchiveWriter
from storage.models import Base


@pytest.mark.asyncio
async def test_recent_observations_returns_role_and_desensitized_messages():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    writer = ArchiveWriter(session_factory)
    await writer.write(
        ArchivePayload(
            request_id="req_observe_1",
            model="gpt-test",
            prompt_original=[{"role": "user", "content": "电话 13812345678"}],
            prompt_desensitized=[{"role": "user", "content": "电话 138****5678"}],
            response={"content": "ok"},
            is_desensitized=True,
            action_taken="desensitized",
            matched_rule_ids=["RG-PHONE-CN"],
        )
    )
    app = FastAPI()
    app.include_router(router, prefix="/admin/api")
    app.state.archive_reader = ArchiveReader(session_factory)
    app.state.settings = Settings(admin_password="strong-local-password")

    with TestClient(app) as client:
        response = client.get(
            "/admin/api/observations/recent",
            auth=("admin", "strong-local-password"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["request_id"] == "req_observe_1"
    assert item["messages_original"][0]["role"] == "user"
    assert item["messages_original"][0]["content"] == "电话 13812345678"
    assert item["messages_desensitized"][0]["content"] == "电话 138****5678"
    assert item["action_taken"] == "desensitized"
    assert item["matched_rule_ids"] == ["RG-PHONE-CN"]
    assert item["completed_at"] is not None

    await engine.dispose()
