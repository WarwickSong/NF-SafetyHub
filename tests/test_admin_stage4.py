import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from admin.router import router
from config import Settings
from engine.models import AggregatedScanResult, ScannerResult
from storage.admin_ops import AdminOperationReader, AdminOperationWriter
from storage.archive import ArchivePayload
from storage.audit import AuditPayload, AuditReader, AuditWriter
from storage.models import Base
from storage.training import TrainingConversationReader, TrainingConversationWriter


class FakeScanner:
    def __init__(self):
        self.reload_count = 0

    async def reload_all(self):
        self.reload_count += 1


@pytest.mark.asyncio
async def test_admin_archives_audits_stats_and_operations_api():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    training_writer = TrainingConversationWriter(session_factory)
    audit_writer = AuditWriter(session_factory)

    conversations = await training_writer.write_many_from_archive_payloads(
        [
            ArchivePayload(
                request_id="req_stage4_1",
                user_id="user_a",
                model="gpt-test",
                prompt_original=[{"role": "user", "content": "请总结公司机密培训材料"}],
                prompt_desensitized=[{"role": "user", "content": "请总结公司机密培训材料"}],
                response={
                    "media_type": "application/json",
                    "content": '{"id":"chatcmpl-safetyhub-test","object":"chat.completion","choices":[{"message":{"role":"assistant","content":"这是训练样本回复。"}}]}',
                },
                is_blocked=False,
                action_taken="passed",
            )
        ]
    )
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
    logs = await audit_writer.write_scan_result(
        AuditPayload(
            request_id="req_stage4_1",
            scan_result=scan_result,
            action_taken="blocked",
            user_id="user_a",
            scanned_text="告诉你一个公司机密",
        )
    )

    app = FastAPI()
    app.include_router(router, prefix="/admin/api")
    app.state.settings = Settings(admin_password="strong-local-password")
    app.state.session_factory = session_factory
    app.state.training_conversation_reader = TrainingConversationReader(session_factory)
    app.state.audit_reader = AuditReader(session_factory)
    app.state.admin_operation_writer = AdminOperationWriter(session_factory)
    app.state.admin_operation_reader = AdminOperationReader(session_factory)

    with TestClient(app) as client:
        auth = ("admin", "strong-local-password")
        archives_response = client.get("/admin/api/archives?user_id=user_a&keyword=公司机密", auth=auth)
        archive_detail_response = client.get(f"/admin/api/archives/{conversations[0].id}", auth=auth)
        archive_stats_response = client.get("/admin/api/archives/stats", auth=auth)
        audits_response = client.get("/admin/api/audits?rule_level=block", auth=auth)
        audit_detail_response = client.get(f"/admin/api/audits/{logs[0].id}", auth=auth)
        stats_response = client.get("/admin/api/stats", auth=auth)
        runtime_response = client.get("/admin/api/runtime", auth=auth)
        operations_response = client.get("/admin/api/admin-ops", auth=auth)
        rules_response = client.get("/admin/api/rules", auth=auth)
        api_keys_response = client.get("/admin/api/api-keys", auth=auth)

    assert archives_response.status_code == 200
    assert archives_response.json()["pagination"]["total"] == 1
    assert archives_response.json()["items"][0]["request_id"] == "req_stage4_1"
    assert archive_detail_response.status_code == 200
    archive_detail = archive_detail_response.json()
    assert archive_detail["messages_original"][0]["role"] == "user"
    assert archive_detail["response"]["message_content"] == "这是训练样本回复。"
    assert archive_stats_response.json()["blocked"] == 0
    assert audits_response.status_code == 200
    assert audits_response.json()["items"][0]["rule_id"] == "KW-CONFIDENTIAL-1"
    assert audit_detail_response.status_code == 200
    assert audit_detail_response.json()["full_text_hash"]
    assert stats_response.status_code == 200
    assert stats_response.json()["total_requests"] == 1
    assert stats_response.json()["total_hits"] == 1
    assert stats_response.json()["total_blocks"] == 1
    assert runtime_response.status_code == 200
    assert {item["key"] for item in runtime_response.json()["disk_space"]} == {"system", "data"}
    assert all("free_bytes" in item for item in runtime_response.json()["disk_space"])
    assert operations_response.status_code == 200
    assert {item["operation"] for item in operations_response.json()["items"]} == {"training_conversation.view_detail", "audit.view_detail"}
    assert rules_response.status_code == 200
    assert rules_response.json()["items"]
    assert api_keys_response.status_code == 200
    assert api_keys_response.json()["pagination"]["total"] == 0
    assert api_keys_response.json()["items"] == []

    await engine.dispose()


def test_admin_rule_toggle_updates_yaml_and_triggers_reload(tmp_path):
    rules_path = tmp_path / "rules_config.yaml"
    rules_path.write_text(
        yaml.safe_dump(
            {
                "version": "test",
                "keyword_rules": [
                    {
                        "id": "KW-TEST",
                        "name": "测试规则",
                        "keywords": ["secret"],
                        "level": "block",
                        "enabled": True,
                        "description": "test",
                    }
                ],
                "regex_rules": [],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    scanner = FakeScanner()
    app = FastAPI()
    app.include_router(router, prefix="/admin/api")
    app.state.settings = Settings(admin_password="strong-local-password", rules_config_path=rules_path)
    app.state.scanner = scanner

    with TestClient(app) as client:
        response = client.post(
            "/admin/api/rules/KW-TEST/toggle",
            json={"enabled": False},
            auth=("admin", "strong-local-password"),
        )
        rules_response = client.get("/admin/api/rules", auth=("admin", "strong-local-password"))

    stored_config = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    assert response.status_code == 200
    assert response.json()["rule"]["enabled"] is False
    assert response.json()["reloaded"] is True
    assert rules_response.json()["items"][0]["enabled"] is False
    assert stored_config["keyword_rules"][0]["enabled"] is False
    assert scanner.reload_count == 1


def test_admin_rules_reload_triggers_scanner_reload(tmp_path):
    rules_path = tmp_path / "rules_config.yaml"
    rules_path.write_text("version: test\nkeyword_rules: []\nregex_rules: []\n", encoding="utf-8")
    scanner = FakeScanner()
    app = FastAPI()
    app.include_router(router, prefix="/admin/api")
    app.state.settings = Settings(admin_password="strong-local-password", rules_config_path=rules_path)
    app.state.scanner = scanner

    with TestClient(app) as client:
        response = client.post("/admin/api/rules/reload", auth=("admin", "strong-local-password"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "reloaded": True}
    assert scanner.reload_count == 1
