from pathlib import Path

import yaml

CONFIG_PATH = Path("engine/rules_config.yaml")


def test_rules_config_keeps_expansion_rule_base():
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert len(data["keyword_rules"]) >= 20
    assert len(data["regex_rules"]) >= 10


def test_rules_config_enables_only_stage2_default_rules():
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    enabled_keyword_rules = [rule for rule in data["keyword_rules"] if rule.get("enabled", True)]
    enabled_regex_rules = [rule for rule in data["regex_rules"] if rule.get("enabled", True)]

    assert {rule["id"] for rule in enabled_keyword_rules} == {
        "KW-CONFIDENTIAL-1",
        "KW-CONFIDENTIAL-2",
        "KW-CONFIDENTIAL-3",
        "KW-CONFIDENTIAL-4",
        "KW-CONFIDENTIAL-5",
    }
    assert all(rule["level"] == "block" for rule in enabled_keyword_rules)
    assert {rule["id"] for rule in enabled_regex_rules} == {"RG-PHONE-CN", "RG-PHONE-INTL"}
    assert all(rule["level"] == "desensitize" for rule in enabled_regex_rules)


def test_rules_config_rule_ids_are_unique():
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    rule_ids = [rule["id"] for rule in data["keyword_rules"] + data["regex_rules"]]

    assert len(rule_ids) == len(set(rule_ids))
