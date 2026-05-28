from pathlib import Path

import pytest

from engine.rules_regex import RegexScanner

CONFIG_PATH = Path("engine/rules_config.yaml")


@pytest.mark.asyncio
async def test_regex_scanner_blocks_phone_number():
    scanner = RegexScanner(CONFIG_PATH)

    results = await scanner.scan("我的手机号是 13812345678，请帮我生成说明")

    assert results
    assert results[0].blocked
    assert results[0].rule_id == "RG-001"
    assert "13812345678" not in results[0].matched_text


@pytest.mark.asyncio
async def test_regex_scanner_warns_email():
    scanner = RegexScanner(CONFIG_PATH)

    results = await scanner.scan("业务邮箱是 security@example.com")

    assert results
    assert results[0].warned
    assert results[0].rule_id == "RG-004"


@pytest.mark.asyncio
async def test_regex_scanner_blocks_api_key():
    scanner = RegexScanner(CONFIG_PATH)

    results = await scanner.scan("sk-abcdefghijklmnopqrstuvwxyz123456")

    assert any(result.rule_id == "RG-003" and result.blocked for result in results)


@pytest.mark.asyncio
async def test_regex_scanner_skips_invalid_patterns(tmp_path):
    config_path = tmp_path / "rules.yaml"
    config_path.write_text(
        "keyword_rules: []\n"
        "regex_rules:\n"
        "  - id: BAD\n"
        "    name: 错误正则\n"
        "    pattern: '['\n"
        "    level: block\n"
        "  - id: GOOD\n"
        "    name: 正确正则\n"
        "    pattern: 'safe-[0-9]+'\n"
        "    level: warn\n",
        encoding="utf-8",
    )
    scanner = RegexScanner(config_path)

    results = await scanner.scan("safe-123")

    assert len(results) == 1
    assert results[0].rule_id == "GOOD"
