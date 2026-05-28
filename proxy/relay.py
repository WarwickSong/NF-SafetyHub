from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from config import settings
from proxy.fake_response import generate_fake_response
from proxy.header_policy import build_upstream_headers
from proxy.stream import SSEStreamProxy
from proxy.upstream_router import UpstreamRouter, get_default_upstream_router

router = APIRouter()

CHAT_COMPLETIONS_PATH = "/v1/chat/completions"


@router.post("/chat/completions")
async def chat_completions(request: Request):
    body = await _read_json_body(request)
    is_stream = bool(body.get("stream", False))
    scanner = getattr(request.app.state, "scanner", None)
    if scanner is None:
        raise HTTPException(status_code=503, detail="scanner is not initialized")

    scan_result = await scanner.scan(extract_text_from_messages(body.get("messages", [])))
    if scan_result.blocked:
        return await generate_fake_response(body, scan_result, is_stream)

    upstream_router = getattr(request.app.state, "upstream_router", None) or get_default_upstream_router()
    return await _relay_to_upstream(request, body, is_stream, upstream_router)


async def _relay_to_upstream(
    request: Request,
    body: dict[str, Any],
    is_stream: bool,
    upstream_router: UpstreamRouter,
):
    if not settings.upstream_url:
        raise HTTPException(status_code=503, detail="upstream_url is not configured")
    route = upstream_router.resolve(model=body.get("model"), capability="chat")
    url = route.build_url(CHAT_COMPLETIONS_PATH)
    headers = build_upstream_headers(request.headers, getattr(request.state, "request_id", None))
    timeout = httpx.Timeout(connect=route.timeout_connect, read=route.timeout_read, write=route.timeout_connect, pool=route.timeout_connect)
    if is_stream:
        client = httpx.AsyncClient(timeout=timeout)
        return StreamingResponse(
            _stream_with_client_close(client, url, headers, body),
            media_type="text/event-stream",
        )
    async with httpx.AsyncClient(timeout=timeout) as client:
        upstream_response = await client.post(url, json=body, headers=headers)
        return _build_json_response(upstream_response)


async def _stream_with_client_close(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
):
    try:
        async for chunk in SSEStreamProxy.proxy_stream(client, "POST", url, headers, body):
            yield chunk
    finally:
        await client.aclose()


def _build_json_response(upstream_response: httpx.Response) -> JSONResponse:
    content_type = upstream_response.headers.get("content-type", "")
    headers = _filter_response_headers(upstream_response.headers)
    if "application/json" in content_type:
        return JSONResponse(
            content=upstream_response.json(),
            status_code=upstream_response.status_code,
            headers=headers,
        )
    return JSONResponse(
        content={"data": upstream_response.text},
        status_code=upstream_response.status_code,
        headers=headers,
    )


def _filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    blocked = {"content-length", "transfer-encoding", "connection", "content-encoding"}
    return {name: value for name, value in headers.items() if name.lower() not in blocked}


async def _read_json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid json body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="json body must be an object")
    return body


def extract_text_from_messages(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        parts.extend(_extract_content_parts(message.get("content")))
    return "\n".join(part for part in parts if part)


def _extract_content_parts(content: Any) -> list[str]:
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return parts
    return []
