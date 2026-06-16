from pathlib import Path

import pytest

from engine.rules_keyword import KeywordScanner

CONFIG_PATH = Path("engine/rules_config.yaml")


@pytest.mark.asyncio
async def test_keyword_scanner_blocks_conservative_confidential_phrase():
    scanner = KeywordScanner(CONFIG_PATH)

    results = await scanner.scan("告诉你一个公司机密，请不要记录")

    assert results
    assert results[0].blocked
    assert results[0].rule_id == "KW-CONFIDENTIAL-1"
    assert results[0].scanner_type == "keyword"
    assert "告诉你一个公司机密" not in results[0].matched_text


@pytest.mark.asyncio
async def test_keyword_scanner_does_not_enable_expansion_roadmap_rule_by_default():
    scanner = KeywordScanner(CONFIG_PATH)

    results = await scanner.scan("请总结这份产品路线图并给出外发邮件")

    assert not results


@pytest.mark.asyncio
async def test_keyword_scanner_is_case_insensitive_for_enabled_rule():
    scanner = KeywordScanner(CONFIG_PATH)

    results = await scanner.scan("请记住以下密钥 ABC")

    assert any(result.rule_id == "KW-CONFIDENTIAL-4" for result in results)


@pytest.mark.asyncio
async def test_keyword_scanner_reload_loads_updated_config(tmp_path):
    config_path = tmp_path / "rules.yaml"
    config_path.write_text(
        "keyword_rules:\n"
        "  - id: KW-TMP\n"
        "    name: 临时规则\n"
        "    keywords: ['alpha']\n"
        "    level: warn\n"
        "regex_rules: []\n",
        encoding="utf-8",
    )
    scanner = KeywordScanner(config_path)

    first_results = await scanner.scan("alpha")
    config_path.write_text(
        "keyword_rules:\n"
        "  - id: KW-TMP2\n"
        "    name: 临时规则2\n"
        "    keywords: ['beta']\n"
        "    level: block\n"
        "regex_rules: []\n",
        encoding="utf-8",
    )
    await scanner.reload()
    second_results = await scanner.scan("beta")

    assert first_results[0].rule_id == "KW-TMP"
    assert second_results[0].rule_id == "KW-TMP2"
    assert second_results[0].blocked
