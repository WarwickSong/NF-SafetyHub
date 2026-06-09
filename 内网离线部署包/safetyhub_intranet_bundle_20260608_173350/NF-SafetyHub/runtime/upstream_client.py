import httpx

from config import settings


def create_upstream_client() -> httpx.AsyncClient:
    timeout = httpx.Timeout(
        connect=settings.upstream_timeout_connect,
        read=settings.upstream_timeout_read,
        write=settings.upstream_timeout_connect,
        pool=settings.upstream_timeout_pool,
    )
    limits = httpx.Limits(
        max_connections=max(1, settings.upstream_max_connections),
        max_keepalive_connections=max(0, settings.upstream_max_keepalive_connections),
        keepalive_expiry=max(1, settings.upstream_keepalive_expiry),
    )
    return httpx.AsyncClient(timeout=timeout, limits=limits)
