from collections.abc import Iterable

from engine.base import BaseScanner
from engine.models import AggregatedScanResult, ScannerResult
from engine.normalizer import TextNormalizer


class ScannerUnavailableError(RuntimeError):
    pass


class ScannerOrchestrator:
    def __init__(self, normalizer: TextNormalizer | None = None, fail_open: bool = False):
        self._scanners: list[BaseScanner] = []
        self._normalizer = normalizer or TextNormalizer()
        self._fail_open = fail_open

    def register(self, scanner: BaseScanner) -> None:
        self._scanners.append(scanner)

    def register_many(self, scanners: Iterable[BaseScanner]) -> None:
        for scanner in scanners:
            self.register(scanner)

    @property
    def scanners(self) -> tuple[BaseScanner, ...]:
        return tuple(self._scanners)

    async def scan(self, text: str) -> AggregatedScanResult:
        normalized_text = self._normalizer.normalize(text)
        all_results: list[ScannerResult] = []
        for scanner in self._scanners:
            try:
                results = await scanner.scan(normalized_text)
            except Exception:
                if not self._fail_open:
                    raise ScannerUnavailableError(f"scanner {scanner.name} failed")
                continue
            all_results.extend(results)
            if any(result.blocked for result in results):
                return AggregatedScanResult(results=all_results, normalized_text=normalized_text)
        return AggregatedScanResult(results=all_results, normalized_text=normalized_text)

    async def reload_all(self) -> None:
        for scanner in self._scanners:
            await scanner.reload()
