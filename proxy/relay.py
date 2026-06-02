from copy import deepcopy
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from config import settings
from proxy.fake_response import generate_fake_response
from proxy.header_policy import build_upstream_headers
from proxy.stream import SSEStreamProxy
from proxy.upstream_router import UpstreamRouter, get_default_upstream_router

router = APIRouter()

CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
JSON_BODY_METHODS = {"POST", "PUT", "PATCH"}
KNOWN_JSON_ENDPOINTS = {
    "/v1/chat/completions",
    "/v1/embeddings",
    "/v1/completions",
    "/v1/responses",
    "/v1/images/generations",
    "/v1/images/edits",
    "/v1/images/variations",
}


@router.post("/chat/completions")
async def chat_completions(request: Request):
    return await relay_openai_compatible(request, "chat/completions")


@router.api_route("/{upstream_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def relay_openai_compatible(request: Request, upstream_path: str):
    upstream_path = upstream_path.strip("/")
    if not upstream_path:
        raise HTTPException(status_code=404, detail="upstream path is required")
    path = f"/v1/{upstream_path}"
    body, raw_body = await _read_request_body(request, path)
    is_stream = isinstance(body, dict) and bool(body.get("stream", False))

    if path == CHAT_COMPLETIONS_PATH:
        scan_text = extract_text_from_request(path, body)
        if scan_text:
            scanner = getattr(request.app.state, "scanner", None)
            if scanner is None:
                raise HTTPException(status_code=503, detail="scanner is not initialized")
            scan_result = await scanner.scan(scan_text)
            if scan_result.blocked and isinstance(body, dict):
                return await generate_fake_response(body, scan_result, is_stream)
            if scan_result.desensitized and isinstance(body, dict):
                body = desensitize_chat_request_body(body)

    upstream_router = getattr(request.app.state, "upstream_router", None) or get_default_upstream_router()
    return await _relay_to_upstream(request, path, body, raw_body, is_stream, upstream_router)


async def _relay_to_upstream(
    request: Request,
    path: str,
    body: Any,
    raw_body: bytes,
    is_stream: bool,
    upstream_router: UpstreamRouter,
):
    if not settings.upstream_url:
        raise HTTPException(status_code=503, detail="upstream_url is not configured")
    model = body.get("model") if isinstance(body, dict) else None
    route = upstream_router.resolve(model=model, capability=_infer_capability(path))
    url = _append_query_string(route.build_url(path), request.url.query)
    headers = build_upstream_headers(request.headers, getattr(request.state, "request_id", None))
    timeout = httpx.Timeout(connect=route.timeout_connect, read=route.timeout_read, write=route.timeout_connect, pool=route.timeout_connect)
    if is_stream and request.method in JSON_BODY_METHODS and isinstance(body, dict):
        client = httpx.AsyncClient(timeout=timeout)
        return StreamingResponse(
            _stream_with_client_close(client, request.method, url, headers, body),
            media_type="text/event-stream",
        )
    async with httpx.AsyncClient(timeout=timeout) as client:
        request_kwargs: dict[str, Any] = {"headers": headers}
        if request.method in JSON_BODY_METHODS:
            if body is not None:
                request_kwargs["json"] = body
            elif raw_body:
                request_kwargs["content"] = raw_body
        upstream_response = await client.request(request.method, url, **request_kwargs)
        return _build_response(upstream_response)


async def _stream_with_client_close(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
):
    try:
        async for chunk in SSEStreamProxy.proxy_stream(client, method, url, headers, body):
            yield chunk
    finally:
        await client.aclose()


def _build_response(upstream_response: httpx.Response) -> Response:
    headers = _filter_response_headers(upstream_response.headers)
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=headers,
        media_type=upstream_response.headers.get("content-type"),
    )


def _filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    blocked = {"content-length", "transfer-encoding", "connection", "content-encoding"}
    return {name: value for name, value in headers.items() if name.lower() not in blocked}


async def _read_request_body(request: Request, path: str) -> tuple[Any, bytes]:
    if request.method not in JSON_BODY_METHODS:
        return None, b""
    raw_body = await request.body()
    if not raw_body:
        return None, raw_body
    content_type = request.headers.get("content-type", "")
    should_parse_json = path in KNOWN_JSON_ENDPOINTS or "application/json" in content_type.lower()
    if not should_parse_json:
        return None, raw_body
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid json body") from exc
    if path in KNOWN_JSON_ENDPOINTS and not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="json body must be an object")
    return body, raw_body


async def _read_json_body(request: Request) -> dict[str, Any]:
    body, _ = await _read_request_body(request, CHAT_COMPLETIONS_PATH)
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="json body must be an object")
    return body


def _append_query_string(url: str, query: str) -> str:
    if not query:
        return url
    parts = urlsplit(url)
    merged_query = f"{parts.query}&{query}" if parts.query else query
    return urlunsplit((parts.scheme, parts.netloc, parts.path, merged_query, parts.fragment))


def _infer_capability(path: str) -> str:
    if path == "/v1/embeddings":
        return "embedding"
    if path.startswith("/v1/images/"):
        return "vision"
    if path.startswith("/v1/files"):
        return "file_upload"
    return "chat"


PHONE_PATTERNS = (
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)\+?[1-9]\d{0,2}[ -]?(?:\d[ -]?){7,14}\d(?!\d)"),
)


def desensitize_chat_request_body(body: dict[str, Any]) -> dict[str, Any]:
    sanitized_body = deepcopy(body)
    messages = sanitized_body.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            message["content"] = desensitize_content(message.get("content"))
    return sanitized_body


def desensitize_content(content: Any) -> Any:
    if isinstance(content, str):
        return desensitize_text(content)
    if isinstance(content, list):
        sanitized_parts = []
        for item in content:
            if isinstance(item, str):
                sanitized_parts.append(desensitize_text(item))
            elif isinstance(item, dict):
                sanitized_item = deepcopy(item)
                if isinstance(sanitized_item.get("text"), str):
                    sanitized_item["text"] = desensitize_text(sanitized_item["text"])
                if "content" in sanitized_item:
                    sanitized_item["content"] = desensitize_content(sanitized_item.get("content"))
                sanitized_parts.append(sanitized_item)
            else:
                sanitized_parts.append(item)
        return sanitized_parts
    return content


def desensitize_text(text: str) -> str:
    sanitized = text
    for pattern in PHONE_PATTERNS:
        sanitized = pattern.sub(_mask_phone_match, sanitized)
    return sanitized


def _mask_phone_match(match: re.Match[str]) -> str:
    value = match.group()
    digits = re.sub(r"\D", "", value)
    if len(digits) <= 7:
        return "*" * len(value)
    return f"{digits[:3]}****{digits[-4:]}"


def extract_text_from_request(path: str, body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    if path == CHAT_COMPLETIONS_PATH:
        return extract_text_from_messages(body.get("messages", []))
    if path == "/v1/embeddings":
        return extract_text_from_value(body.get("input"))
    if path == "/v1/completions":
        return extract_text_from_value(body.get("prompt"))
    if path == "/v1/responses":
        return "\n".join(
            part for part in [
                extract_text_from_value(body.get("input")),
                extract_text_from_messages(body.get("messages", [])),
            ] if part
        )
    if path.startswith("/v1/images/"):
        return extract_text_from_value(body.get("prompt"))
    return extract_text_from_value(body)


def extract_text_from_messages(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        parts.extend(_extract_content_parts(message.get("content")))
    return "\n".join(part for part in parts if part)


def extract_text_from_value(value: Any) -> str:
    parts: list[str] = []
    _collect_text(value, parts)
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
                elif "content" in item:
                    parts.extend(_extract_content_parts(item.get("content")))
        return parts
    return []


def _collect_text(value: Any, parts: list[str]) -> None:
    if isinstance(value, str):
        parts.append(value)
        return
    if isinstance(value, list):
        for item in value:
            _collect_text(item, parts)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_text(item, parts)
