from dataclasses import dataclass
import time
from typing import Any

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from config import settings
from governance.api_keys import ApiKeyService, is_record_active
from storage.models import ApiKeyRecord


@dataclass(slots=True)
class RequestIdentity:
    api_key_id: str = ""
    user_id: str = ""
    upstream_api_key: str = ""
    key_prefix: str = ""


class ApiKeyIdentityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key_count_cache_seconds: float = 5):
        super().__init__(app)
        self._api_key_count_cache_seconds = max(0, api_key_count_cache_seconds)
        self._api_key_count_cache_until = 0.0
        self._api_key_count_cache_value: int | None = None

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)
        service = _api_key_service(request)
        api_key_count = await self._api_key_count(service)
        if api_key_count == 0 and settings.allow_empty_api_keys_passthrough:
            request.state.identity = RequestIdentity()
            return await call_next(request)
        if api_key_count == 0:
            return _unauthorized("api key is required")
        raw_key = _extract_bearer_key(request.headers.get("authorization", ""))
        if not raw_key:
            return _unauthorized("missing api key")
        record = await service.find_by_raw_key(raw_key)
        if record is None or not is_record_active(record):
            return _unauthorized("invalid api key")
        request.state.identity = await _build_identity(service, record)
        return await call_next(request)

    async def _api_key_count(self, service: ApiKeyService) -> int:
        if self._api_key_count_cache_seconds <= 0:
            return await service.count()
        now = time.monotonic()
        if self._api_key_count_cache_value is not None and now < self._api_key_count_cache_until:
            return self._api_key_count_cache_value
        count = await service.count()
        self._api_key_count_cache_value = count
        self._api_key_count_cache_until = now + self._api_key_count_cache_seconds
        return count


async def require_request_identity(request: Request, body: Any, capability: str) -> RequestIdentity:
    identity = getattr(request.state, "identity", None)
    if not isinstance(identity, RequestIdentity):
        request.state.identity = RequestIdentity()
        return request.state.identity
    return identity


def _api_key_service(request: Request) -> ApiKeyService:
    return getattr(request.app.state, "api_key_service", None) or ApiKeyService(getattr(request.app.state, "session_factory", None))


async def _build_identity(service: ApiKeyService, record: ApiKeyRecord) -> RequestIdentity:
    return RequestIdentity(
        api_key_id=record.id,
        user_id=record.owner_user_id,
        upstream_api_key=await service.decrypt_upstream_key(record),
        key_prefix=record.key_prefix,
    )


def _extract_bearer_key(value: str) -> str:
    if not value:
        return ""
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return ""
    return token.strip()


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": detail})
