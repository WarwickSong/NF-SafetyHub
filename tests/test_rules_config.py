from pathlib import Path

import yaml

CONFIG_PATH = Path("engine/rules_config.yaml")


def test_rules_config_has_required_initial_rule_counts():
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert len(data["keyword_rules"]) >= 20
    assert len(data["regex_rules"]) >= 10


def test_rules_config_rule_ids_are_unique():
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    rule_ids = [rule["id"] for rule in data["keyword_rules"] + data["regex_rules"]]

    assert len(rule_ids) == len(set(rule_ids))
