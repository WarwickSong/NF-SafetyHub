from collections.abc import AsyncGenerator

import httpx
from starlette.responses import JSONResponse


class SSEStreamProxy:
    @staticmethod
    async def proxy_stream(
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict | None = None,
        raw_body: bytes | None = None,
    ) -> AsyncGenerator[bytes, None]:
        request_kwargs: dict = {"headers": headers}
        if raw_body is not None:
            request_kwargs["content"] = raw_body
        elif body is not None:
            request_kwargs["json"] = body
        try:
            async with client.stream(method, url, **request_kwargs) as upstream:
                if upstream.status_code >= 400:
                    content = await upstream.aread()
                    yield _build_error_event(upstream.status_code, content, upstream.headers.get("content-type"))
                    return
                async for chunk in upstream.aiter_bytes():
                    if chunk:
                        yield chunk
        except httpx.PoolTimeout as exc:
            yield _build_error_event(429, _upstream_error_content(exc, "upstream connection pool exhausted"), "application/json")
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.TimeoutException) as exc:
            yield _build_error_event(504, _upstream_error_content(exc, "upstream request timed out"), "application/json")
        except httpx.TransportError as exc:
            yield _build_error_event(502, _upstream_error_content(exc, "upstream transport error"), "application/json")

    @staticmethod
    async def collect_stream(
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict | None = None,
        raw_body: bytes | None = None,
    ) -> AsyncGenerator[tuple[bytes | None, str | None], None]:
        chunks: list[bytes] = []
        async for chunk in SSEStreamProxy.proxy_stream(client, method, url, headers, body, raw_body):
            chunks.append(chunk)
            yield chunk, None
        yield None, b"".join(chunks).decode("utf-8", errors="replace")


def _upstream_error_content(exc: httpx.HTTPError, detail: str) -> bytes:
    response = JSONResponse(content={"detail": detail, "error_type": exc.__class__.__name__})
    return response.body


def _build_error_event(status_code: int, content: bytes, content_type: str | None = None) -> bytes:
    payload = {
        "error": {
            "status_code": status_code,
            "content_type": content_type or "application/octet-stream",
            "body": content.decode("utf-8", errors="replace"),
        }
    }
    response = JSONResponse(content=payload)
    return b"event: error\n" + b"data: " + response.body + b"\n\n"
