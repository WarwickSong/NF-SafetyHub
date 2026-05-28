from pathlib import Path

import pytest

from engine.base import BaseScanner
from engine.models import ScannerResult
from engine.normalizer import normalize_text
from engine.rules_keyword import KeywordScanner
from engine.rules_regex import RegexScanner
from engine.scanner import ScannerOrchestrator

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

    result = await orchestrator.scan("请外发产品路线图，手机号是 13812345678")

    assert result.blocked
    assert result.action == "blocked"
    assert result.block_result.rule_id == "KW-001"
    assert all(scan_result.scanner_type == "keyword" for scan_result in result.results)


@pytest.mark.asyncio
async def test_scanner_orchestrator_collects_warn_and_continues():
    orchestrator = ScannerOrchestrator()
    orchestrator.register(KeywordScanner(CONFIG_PATH))
    orchestrator.register(RegexScanner(CONFIG_PATH))

    result = await orchestrator.scan("internal endpoint 是 192.168.1.20，邮箱 security@example.com")

    assert not result.blocked
    assert result.warned
    assert len(result.warn_results) >= 2
    assert {warn.rule_id for warn in result.warn_results} >= {"KW-004", "RG-004"}


@pytest.mark.asyncio
async def test_scanner_orchestrator_degrades_when_scanner_fails():
    orchestrator = ScannerOrchestrator()
    orchestrator.register(ErrorScanner())
    orchestrator.register(KeywordScanner(CONFIG_PATH))

    result = await orchestrator.scan("产品路线图")

    assert result.blocked
    assert result.block_result.rule_id == "KW-001"


def test_normalize_text_decodes_url_and_removes_zero_width_chars():
    normalized = normalize_text("%E4%BA%A7%E5%93%81%E2%80%8B%E8%B7%AF%E7%BA%BF%E5%9B%BE")

    assert normalized == "产品路线图"


def test_normalize_text_unifies_full_width_characters():
    normalized = normalize_text("ｐａｓｓｗｏｒｄ＝123")

    assert normalized == "password=123"
