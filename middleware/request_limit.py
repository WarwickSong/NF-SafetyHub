from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import Message

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
        request = _limited_request(request, max_bytes)
        try:
            return await call_next(request)
        except RequestBodyTooLarge:
            return _too_large_response(max_bytes)


class RequestBodyTooLarge(Exception):
    pass


def _limited_request(request: Request, max_bytes: int) -> Request:
    received = 0
    receive = request.receive

    async def limited_receive() -> Message:
        nonlocal received
        message = await receive()
        if message["type"] != "http.request":
            return message
        body = message.get("body", b"")
        received += len(body)
        if received > max_bytes:
            raise RequestBodyTooLarge
        return message

    return Request(request.scope, limited_receive)


def _too_large_response(max_bytes: int) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={"detail": f"request body exceeds limit of {max_bytes} bytes"},
    )
