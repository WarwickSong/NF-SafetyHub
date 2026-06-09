from pathlib import Path

import pytest

from engine.rules_regex import RegexScanner

CONFIG_PATH = Path("engine/rules_config.yaml")


@pytest.mark.asyncio
async def test_regex_scanner_desensitizes_cn_phone_number():
    scanner = RegexScanner(CONFIG_PATH)

    results = await scanner.scan("我的手机号是 13812345678，请帮我生成说明")

    assert results
    assert results[0].desensitized
    assert results[0].rule_id == "RG-PHONE-CN"
    assert "13812345678" not in results[0].matched_text


@pytest.mark.asyncio
async def test_regex_scanner_desensitizes_international_phone_number():
    scanner = RegexScanner(CONFIG_PATH)

    results = await scanner.scan("联系电话是 +1 415 555 2671")

    assert results
    assert any(result.rule_id == "RG-PHONE-INTL" and result.desensitized for result in results)


@pytest.mark.asyncio
async def test_regex_scanner_keeps_expansion_email_rule_disabled_by_default():
    scanner = RegexScanner(CONFIG_PATH)

    results = await scanner.scan("业务邮箱是 security@example.com")

    assert not results


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
