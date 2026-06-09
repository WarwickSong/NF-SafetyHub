from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from config import settings


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        max_bytes = max(1, settings.request_max_body_mb) * 1024 * 1024
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    return _too_large_response(max_bytes)
            except ValueError:
                return _too_large_response(max_bytes)
        return await call_next(request)


def _too_large_response(max_bytes: int) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={"detail": f"request body exceeds limit of {max_bytes} bytes"},
    )
