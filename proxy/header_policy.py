from collections.abc import Mapping

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

BLOCKED_HEADERS = {
    "host",
    "cookie",
    "content-length",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
}

INTERNAL_HEADER_PREFIXES = (
    "x-safetyhub-",
    "x-admin-",
    "x-internal-",
)


class HeaderPolicy:
    def __init__(self, blocked_headers: set[str] | None = None):
        self._blocked_headers = {header.lower() for header in (blocked_headers or set())}

    def build_upstream_headers(self, headers: Mapping[str, str], request_id: str | None = None) -> dict[str, str]:
        upstream_headers: dict[str, str] = {}
        for name, value in headers.items():
            normalized_name = name.lower()
            if self._should_strip(normalized_name):
                continue
            upstream_headers[name] = value
        if request_id:
            upstream_headers["X-Request-ID"] = request_id
        return upstream_headers

    def _should_strip(self, normalized_name: str) -> bool:
        if normalized_name in HOP_BY_HOP_HEADERS:
            return True
        if normalized_name in BLOCKED_HEADERS:
            return True
        if normalized_name in self._blocked_headers:
            return True
        return normalized_name.startswith(INTERNAL_HEADER_PREFIXES)


def build_upstream_headers(headers: Mapping[str, str], request_id: str | None = None) -> dict[str, str]:
    return HeaderPolicy().build_upstream_headers(headers, request_id)
