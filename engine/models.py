from dataclasses import dataclass, field


@dataclass(slots=True)
class ScannerResult:
    hit: bool
    rule_id: str = ""
    rule_name: str = ""
    level: str = "pass"
    matched_text: str = ""
    position: tuple[int, int] = (0, 0)
    scanner_type: str = ""
    description: str = ""

    @property
    def blocked(self) -> bool:
        return self.hit and self.level == "block"

    @property
    def warned(self) -> bool:
        return self.hit and self.level == "warn"

    @property
    def desensitized(self) -> bool:
        return self.hit and self.level == "desensitize"

    @property
    def passed(self) -> bool:
        return not self.hit or self.level == "pass"


@dataclass(slots=True)
class AggregatedScanResult:
    results: list[ScannerResult] = field(default_factory=list)
    normalized_text: str = ""

    @property
    def hit(self) -> bool:
        return any(result.hit for result in self.results)

    @property
    def blocked(self) -> bool:
        return any(result.blocked for result in self.results)

    @property
    def warned(self) -> bool:
        return any(result.warned for result in self.results)

    @property
    def desensitized(self) -> bool:
        return any(result.desensitized for result in self.results)

    @property
    def block_result(self) -> ScannerResult | None:
        return next((result for result in self.results if result.blocked), None)

    @property
    def desensitize_results(self) -> list[ScannerResult]:
        return [result for result in self.results if result.desensitized]

    @property
    def warn_results(self) -> list[ScannerResult]:
        return [result for result in self.results if result.warned]

    @property
    def action(self) -> str:
        if self.blocked:
            return "blocked"
        if self.desensitized:
            return "desensitized"
        if self.warned:
            return "warned"
        return "passed"
