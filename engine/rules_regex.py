from pathlib import Path
import re

import yaml

from engine.base import BaseScanner
from engine.models import ScannerResult


class RegexScanner(BaseScanner):
    def __init__(self, config_path: Path | str):
        self._config_path = Path(config_path)
        self._rules: list[dict] = []
        self._compiled: list[tuple[re.Pattern[str], dict]] = []
        self._load_rules()

    @property
    def name(self) -> str:
        return "regex"

    async def scan(self, text: str) -> list[ScannerResult]:
        results: list[ScannerResult] = []
        for pattern, rule in self._compiled:
            match = pattern.search(text)
            if not match:
                continue
            results.append(self._build_result(rule, match))
        return results

    async def reload(self) -> None:
        self._load_rules()

    def _load_rules(self) -> None:
        if not self._config_path.exists():
            self._rules = []
            self._compiled = []
            return
        with self._config_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        self._rules = data.get("regex_rules", []) or []
        self._compiled = self._compile_rules(self._rules)

    def _compile_rules(self, rules: list[dict]) -> list[tuple[re.Pattern[str], dict]]:
        compiled: list[tuple[re.Pattern[str], dict]] = []
        for rule in rules:
            if not rule.get("enabled", True):
                continue
            flags = 0
            if rule.get("ignore_case", False):
                flags |= re.IGNORECASE
            try:
                compiled.append((re.compile(rule["pattern"], flags), rule))
            except (KeyError, re.error):
                continue
        return compiled

    def _build_result(self, rule: dict, match: re.Match[str]) -> ScannerResult:
        return ScannerResult(
            hit=True,
            rule_id=rule.get("id", ""),
            rule_name=rule.get("name", ""),
            level=rule.get("level", "block"),
            matched_text=self._mask_text(match.group()),
            position=match.span(),
            scanner_type=self.name,
            description=rule.get("description", ""),
        )

    @staticmethod
    def _mask_text(text: str) -> str:
        if not text:
            return ""
        if len(text) <= 4:
            return text[0] + "*" * (len(text) - 1)
        return text[:2] + "*" * (len(text) - 4) + text[-2:]
