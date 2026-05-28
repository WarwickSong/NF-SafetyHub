from dataclasses import dataclass
from urllib.parse import urljoin

from config import settings


@dataclass(frozen=True, slots=True)
class UpstreamRoute:
    base_url: str
    timeout_connect: int
    timeout_read: int

    def build_url(self, path: str) -> str:
        return urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))


class UpstreamRouter:
    def __init__(self, default_url: str, timeout_connect: int = 10, timeout_read: int = 120):
        self._default_route = UpstreamRoute(
            base_url=default_url,
            timeout_connect=timeout_connect,
            timeout_read=timeout_read,
        )

    def resolve(self, model: str | None = None, api_key_id: str | None = None, capability: str = "chat") -> UpstreamRoute:
        return self._default_route


def get_default_upstream_router() -> UpstreamRouter:
    return UpstreamRouter(
        default_url=settings.upstream_url,
        timeout_connect=settings.upstream_timeout_connect,
        timeout_read=settings.upstream_timeout_read,
    )
