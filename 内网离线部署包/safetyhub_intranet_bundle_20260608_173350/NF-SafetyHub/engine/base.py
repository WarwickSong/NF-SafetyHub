from abc import ABC, abstractmethod

from engine.models import ScannerResult


class BaseScanner(ABC):
    @abstractmethod
    async def scan(self, text: str) -> list[ScannerResult]:
        raise NotImplementedError

    @abstractmethod
    async def reload(self) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError
