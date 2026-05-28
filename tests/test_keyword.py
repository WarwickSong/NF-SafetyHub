from pathlib import Path

import pytest

from engine.rules_keyword import KeywordScanner

CONFIG_PATH = Path("engine/rules_config.yaml")


@pytest.mark.asyncio
async def test_keyword_scanner_blocks_product_roadmap():
    scanner = KeywordScanner(CONFIG_PATH)

    results = await scanner.scan("请总结这份产品路线图并给出外发邮件")

    assert results
    assert results[0].blocked
    assert results[0].rule_id == "KW-001"
    assert results[0].scanner_type == "keyword"
    assert "产品路线图" not in results[0].matched_text


@pytest.mark.asyncio
async def test_keyword_scanner_is_case_insensitive():
    scanner = KeywordScanner(CONFIG_PATH)

    results = await scanner.scan("The ROADMAP should not be shared externally")

    assert any(result.rule_id == "KW-001" for result in results)


@pytest.mark.asyncio
async def test_keyword_scanner_warns_internal_information():
    scanner = KeywordScanner(CONFIG_PATH)

    results = await scanner.scan("这里包含一个 internal endpoint，需要确认能否外发")

    assert results
    assert results[0].warned
    assert results[0].rule_id == "KW-004"


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
