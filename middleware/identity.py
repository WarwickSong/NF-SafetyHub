from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from governance.api_keys import ApiKeyService, is_record_active
from storage.models import ApiKeyRecord


@dataclass(slots=True)
class RequestIdentity:
    api_key_id: str = ""
    user_id: str = ""
    upstream_api_key: str = ""
    key_prefix: str = ""


class ApiKeyIdentityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)
        service = _api_key_service(request)
        if await service.count() == 0:
            request.state.identity = RequestIdentity()
            return await call_next(request)
        raw_key = _extract_bearer_key(request.headers.get("authorization", ""))
        if not raw_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing api key")
        record = await service.find_by_raw_key(raw_key)
        if record is None or not is_record_active(record):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")
        request.state.identity = await _build_identity(service, record)
        return await call_next(request)


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
