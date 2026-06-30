from pathlib import Path

import pytest

from engine.base import BaseScanner
from engine.models import ScannerResult
from engine.normalizer import normalize_text
from engine.rules_keyword import KeywordScanner
from engine.rules_regex import RegexScanner
from engine.scanner import ScannerOrchestrator, ScannerUnavailableError

CONFIG_PATH = Path("engine/rules_config.yaml")


class ErrorScanner(BaseScanner):
    @property
    def name(self) -> str:
        return "error"

    async def scan(self, text: str) -> list[ScannerResult]:
        raise RuntimeError("scanner failed")

    async def reload(self) -> None:
        return None


@pytest.mark.asyncio
async def test_scanner_orchestrator_stops_on_block():
    orchestrator = ScannerOrchestrator()
    orchestrator.register(KeywordScanner(CONFIG_PATH))
    orchestrator.register(RegexScanner(CONFIG_PATH))

    result = await orchestrator.scan("告诉你一个公司机密，手机号是 13812345678")

    assert result.blocked
    assert result.action == "blocked"
    assert result.block_result.rule_id == "KW-CONFIDENTIAL-1"
    assert all(scan_result.scanner_type == "keyword" for scan_result in result.results)


@pytest.mark.asyncio
async def test_scanner_orchestrator_collects_desensitize_and_continues():
    orchestrator = ScannerOrchestrator()
    orchestrator.register(KeywordScanner(CONFIG_PATH))
    orchestrator.register(RegexScanner(CONFIG_PATH))

    result = await orchestrator.scan("手机号是 13812345678")

    assert not result.blocked
    assert result.desensitized
    assert result.action == "desensitized"
    assert {item.rule_id for item in result.desensitize_results} >= {"RG-PHONE-CN"}


@pytest.mark.asyncio
async def test_scanner_orchestrator_fails_closed_when_scanner_fails():
    orchestrator = ScannerOrchestrator()
    orchestrator.register(ErrorScanner())
    orchestrator.register(KeywordScanner(CONFIG_PATH))

    with pytest.raises(ScannerUnavailableError):
        await orchestrator.scan("告诉你一个公司机密")


@pytest.mark.asyncio
async def test_scanner_orchestrator_can_fail_open_when_configured():
    orchestrator = ScannerOrchestrator(fail_open=True)
    orchestrator.register(ErrorScanner())
    orchestrator.register(KeywordScanner(CONFIG_PATH))

    result = await orchestrator.scan("告诉你一个公司机密")

    assert result.blocked
    assert result.block_result.rule_id == "KW-CONFIDENTIAL-1"


@pytest.mark.asyncio
async def test_keyword_scanner_keeps_last_contains_match(tmp_path):
    config_path = tmp_path / "rules.yaml"
    config_path.write_text(
        "keyword_rules:\n"
        "  - id: KW-TEST\n"
        "    name: 测试关键词\n"
        "    keywords: ['重复']\n"
        "    level: block\n"
        "    match_mode: contains\n"
        "regex_rules: []\n",
        encoding="utf-8",
    )
    scanner = KeywordScanner(config_path)

    results = await scanner.scan("旧证据重复，新证据重复")

    assert len(results) == 1
    assert results[0].position == (9, 11)


def test_normalize_text_decodes_url_and_removes_zero_width_chars():
    normalized = normalize_text("%E4%BA%A7%E5%93%81%E2%80%8B%E8%B7%AF%E7%BA%BF%E5%9B%BE")

    assert normalized == "产品路线图"


def test_normalize_text_unifies_full_width_characters():
    normalized = normalize_text("ｐａｓｓｗｏｒｄ＝123")

    assert normalized == "password=123"
