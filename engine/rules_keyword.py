from pathlib import Path

import yaml

from engine.base import BaseScanner
from engine.models import ScannerResult


class KeywordScanner(BaseScanner):
    def __init__(self, config_path: Path | str):
        self._config_path = Path(config_path)
        self._rules: list[dict] = []
        self._load_rules()

    @property
    def name(self) -> str:
        return "keyword"

    async def scan(self, text: str) -> list[ScannerResult]:
        results: list[ScannerResult] = []
        for rule in self._enabled_rules():
            results.extend(self._scan_rule(text, rule))
        return results

    async def reload(self) -> None:
        self._load_rules()

    def _load_rules(self) -> None:
        if not self._config_path.exists():
            self._rules = []
            return
        with self._config_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        self._rules = data.get("keyword_rules", []) or []

    def _enabled_rules(self) -> list[dict]:
        return [rule for rule in self._rules if rule.get("enabled", True)]

    def _scan_rule(self, text: str, rule: dict) -> list[ScannerResult]:
        case_sensitive = rule.get("case_sensitive", False)
        match_mode = rule.get("match_mode", "contains")
        search_text = text if case_sensitive else text.lower()
        results: list[ScannerResult] = []
        for keyword in rule.get("keywords", []):
            search_keyword = keyword if case_sensitive else keyword.lower()
            position = self._match_position(search_text, search_keyword, match_mode)
            if position is None:
                continue
            results.append(self._build_result(rule, keyword, position))
            if rule.get("stop_on_first", True):
                break
        return results

    def _match_position(self, text: str, keyword: str, match_mode: str) -> tuple[int, int] | None:
        if not keyword:
            return None
        if match_mode == "exact":
            return (0, len(text)) if text == keyword else None
        if match_mode == "prefix":
            return (0, len(keyword)) if text.startswith(keyword) else None
        index = text.rfind(keyword)
        if index == -1:
            return None
        return index, index + len(keyword)

    def _build_result(self, rule: dict, keyword: str, position: tuple[int, int]) -> ScannerResult:
        return ScannerResult(
            hit=True,
            rule_id=rule.get("id", ""),
            rule_name=rule.get("name", ""),
            level=rule.get("level", "block"),
            matched_text=self._mask_text(keyword),
            position=position,
            scanner_type=self.name,
            description=rule.get("description", ""),
        )

    @staticmethod
    def _mask_text(text: str) -> str:
        if not text:
            return ""
        if len(text) == 1:
            return "*"
        if len(text) == 2:
            return text[0] + "*"
        return text[0] + "*" * (len(text) - 2) + text[-1]
