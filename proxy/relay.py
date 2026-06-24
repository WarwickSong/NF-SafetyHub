import asyncio
from copy import deepcopy
import json
import re
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.requests import ClientDisconnect

from config import settings
from engine.models import AggregatedScanResult
from middleware.identity import RequestIdentity, require_request_identity
from proxy.fake_response import generate_fake_response
from proxy.header_policy import build_upstream_headers, filter_response_headers
from proxy.stream import SSEStreamProxy
from proxy.upstream_router import UpstreamRouter, get_default_upstream_router
from storage.archive import ArchivePayload
from storage.audit import AuditPayload, AuditWriter
from storage.image_assets import ImageAssetArchiver, extract_image_asset_sources
from storage.training import TrainingConversationWriter

STREAM_ARCHIVE_ENCODING = "utf-8"

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
    started_at = perf_counter()
    upstream_path = upstream_path.strip("/")
    if not upstream_path:
        raise HTTPException(status_code=404, detail="upstream path is required")
    path = f"/v1/{upstream_path}"
    body, raw_body = await _read_request_body(request, path)
    capability = _infer_capability(path)
    identity = await require_request_identity(request, body, capability)
    original_body = deepcopy(body) if isinstance(body, dict) else body
    is_stream = isinstance(body, dict) and bool(body.get("stream", False))
    scan_result: AggregatedScanResult | None = None
    latest_scan_text = ""
    latest_desensitized_text = ""
    was_desensitized = False

    if path == CHAT_COMPLETIONS_PATH:
        latest_scan_text = extract_latest_text_from_request(path, body)
        if latest_scan_text:
            scanner = getattr(request.app.state, "scanner", None)
            if scanner is None:
                raise HTTPException(status_code=503, detail="scanner is not initialized")
            scan_result = await scanner.scan(latest_scan_text)
            if scan_result.blocked and isinstance(body, dict):
                fake_response = await generate_fake_response(body, scan_result, is_stream)
                _write_chat_audit(request, scan_result, latest_scan_text, "blocked", identity)
                _write_chat_archive(request, original_body, body, _response_archive_body(fake_response), scan_result, "blocked", is_stream, started_at, identity)
                return fake_response
        if isinstance(body, dict):
            desensitized_body = desensitize_chat_request_body(body)
            was_desensitized = desensitized_body != body
            latest_desensitized_text = extract_latest_text_from_request(path, desensitized_body) if was_desensitized else ""
            body = desensitized_body

    upstream_router = getattr(request.app.state, "upstream_router", None) or get_default_upstream_router()
    action_taken = _action_from_scan_result(scan_result, was_desensitized) if path == CHAT_COMPLETIONS_PATH else "passed"
    if path == CHAT_COMPLETIONS_PATH:
        _write_chat_audit(request, scan_result, latest_scan_text, action_taken, identity, latest_desensitized_text)
    response = await _relay_to_upstream(
        request,
        path,
        body,
        raw_body,
        is_stream,
        upstream_router,
        original_body,
        scan_result,
        action_taken,
        started_at,
        identity,
        capability,
    )
    if path == CHAT_COMPLETIONS_PATH and not is_stream:
        _write_chat_archive(request, original_body, body, _response_archive_body(response), scan_result, action_taken, is_stream, started_at, identity)
    elif path.startswith("/v1/images/"):
        await _write_image_archive(request, original_body, response, started_at, identity)
    return response


async def _relay_to_upstream(
    request: Request,
    path: str,
    body: Any,
    raw_body: bytes,
    is_stream: bool,
    upstream_router: UpstreamRouter,
    original_body: Any = None,
    scan_result: AggregatedScanResult | None = None,
    action_taken: str = "passed",
    started_at: float = 0,
    identity: RequestIdentity | None = None,
    capability: str = "chat",
):
    if not settings.upstream_url:
        raise HTTPException(status_code=503, detail="upstream_url is not configured")
    model = body.get("model") if isinstance(body, dict) else None
    route = upstream_router.resolve(model=model, capability=capability)
    url = _append_query_string(route.build_url(path), request.url.query)
    upstream_api_key = identity.upstream_api_key if identity and identity.upstream_api_key else None
    headers = build_upstream_headers(request.headers, getattr(request.state, "request_id", None), upstream_api_key)
    if is_stream:
        headers = _with_stream_headers(headers)
    client = getattr(request.app.state, "upstream_client", None)
    client_owner = False
    if client is None:
        timeout = httpx.Timeout(connect=route.timeout_connect, read=route.timeout_read, write=route.timeout_connect, pool=settings.upstream_timeout_pool)
        client = httpx.AsyncClient(timeout=timeout)
        client_owner = True
    relay_body, relay_raw_body = _select_relay_payload(request.method, body, raw_body, action_taken)
    if is_stream and request.method in JSON_BODY_METHODS and isinstance(body, dict):
        stream = _stream_with_archive(
            client,
            client_owner,
            request.method,
            url,
            headers,
            relay_body,
            relay_raw_body,
            request,
            original_body,
            scan_result,
            action_taken,
            started_at,
            identity,
        ) if path == CHAT_COMPLETIONS_PATH else _stream_with_client_close(
            client,
            client_owner,
            request.method,
            url,
            headers,
            relay_body,
            relay_raw_body,
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    try:
        request_kwargs: dict[str, Any] = {"headers": headers}
        if request.method in JSON_BODY_METHODS:
            if relay_raw_body is not None:
                request_kwargs["content"] = relay_raw_body
            elif relay_body is not None:
                request_kwargs["json"] = relay_body
        try:
            upstream_response = await client.request(request.method, url, **request_kwargs)
        except httpx.PoolTimeout as exc:
            return _build_upstream_error_response(exc, 429, "upstream connection pool exhausted")
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.TimeoutException) as exc:
            return _build_upstream_error_response(exc, 504, "upstream request timed out")
        except httpx.TransportError as exc:
            return _build_upstream_error_response(exc, 502, "upstream transport error")
        return _build_response(upstream_response)
    finally:
        if client_owner:
            await client.aclose()


def _override_header_case_insensitive(headers: dict[str, str], name: str, value: str) -> dict[str, str]:
    updated_headers = {key: header_value for key, header_value in headers.items() if key.lower() != name.lower()}
    updated_headers[name] = value
    return updated_headers


def _with_stream_headers(headers: dict[str, str]) -> dict[str, str]:
    updated_headers = _override_header_case_insensitive(headers, "Accept", "text/event-stream")
    updated_headers = _override_header_case_insensitive(updated_headers, "Accept-Encoding", "identity")
    return _override_header_case_insensitive(updated_headers, "Cache-Control", "no-cache")


def _select_relay_payload(
    method: str,
    body: Any,
    raw_body: bytes,
    action_taken: str,
) -> tuple[Any, bytes | None]:
    """决定转发上游时使用脱敏后的 dict 还是原始字节。

    - 脱敏分支：用 dict 让 httpx 重新序列化，确保上游收到脱敏后的字节。
    - 其它分支：优先透传 raw_body，保留客户端字节形态。

    Returns:
        二元组 (body_for_json, raw_body_for_content)；任一非 None 表示采用对应字段。
    """

    if method not in JSON_BODY_METHODS:
        return None, None
    if action_taken == "desensitized" and isinstance(body, dict):
        return body, None
    if raw_body:
        return None, raw_body
    if body is not None:
        return body, None
    return None, None


async def _stream_with_client_close(
    client: httpx.AsyncClient,
    client_owner: bool,
    method: str,
    url: str,
    headers: dict[str, str],
    body: Any,
    raw_body: bytes | None,
):
    try:
        async for chunk in SSEStreamProxy.proxy_stream(client, method, url, headers, body, raw_body):
            yield chunk
    finally:
        if client_owner:
            await client.aclose()


async def _stream_with_archive(
    client: httpx.AsyncClient,
    client_owner: bool,
    method: str,
    url: str,
    headers: dict[str, str],
    body: Any,
    raw_body: bytes | None,
    request: Request,
    original_body: Any,
    scan_result: AggregatedScanResult | None,
    action_taken: str,
    started_at: float,
    identity: RequestIdentity | None = None,
):
    collector = StreamArchiveCollector(settings.stream_archive_max_bytes)
    archive_body = body if isinstance(body, dict) else original_body
    try:
        async for chunk in SSEStreamProxy.proxy_stream(client, method, url, headers, body, raw_body):
            collector.add(chunk)
            yield chunk
    finally:
        payload = collector.payload()
        _write_chat_archive(request, original_body, archive_body, payload, scan_result, action_taken, True, started_at, identity)
        if client_owner:
            await client.aclose()


def _build_response(upstream_response: httpx.Response) -> Response:
    headers = filter_response_headers(upstream_response.headers)
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=headers,
        media_type=upstream_response.headers.get("content-type"),
    )


def _build_upstream_error_response(exc: httpx.HTTPError, status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "error_type": exc.__class__.__name__},
    )


def _filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    return filter_response_headers(headers)


def _action_from_scan_result(scan_result: AggregatedScanResult | None, was_desensitized: bool = False) -> str:
    if scan_result is not None and scan_result.blocked:
        return "blocked"
    if was_desensitized:
        return "desensitized"
    if scan_result is None:
        return "passed"
    return scan_result.action


def _response_archive_body(response: Response | StreamingResponse) -> Any:
    if isinstance(response, StreamingResponse):
        return {"stream": True}
    media_type = response.media_type or ""
    content = response.body.decode("utf-8", errors="replace") if isinstance(response.body, bytes) else response.body
    return {"media_type": media_type, "content": content}


class StreamArchiveCollector:
    def __init__(self, max_bytes: int):
        self._max_bytes = max(1, max_bytes)
        self._chunks: list[bytes] = []
        self._archived_bytes = 0
        self._original_bytes = 0

    def add(self, chunk: bytes) -> None:
        self._original_bytes += len(chunk)
        remaining = self._max_bytes - self._archived_bytes
        if remaining <= 0:
            return
        archived_chunk = chunk[:remaining]
        self._chunks.append(archived_chunk)
        self._archived_bytes += len(archived_chunk)

    def payload(self) -> dict[str, Any]:
        content_bytes = b"".join(self._chunks)
        raw_content = content_bytes.decode(STREAM_ARCHIVE_ENCODING, errors="replace")
        return {
            "stream": True,
            "media_type": "text/event-stream",
            "content": raw_content,
            "message_content": _extract_sse_message_content(raw_content),
            "truncated": self._original_bytes > self._max_bytes,
            "archived_bytes": self._archived_bytes,
            "original_bytes": self._original_bytes,
        }


def _stream_archive_body(chunks: list[bytes]) -> dict[str, Any]:
    collector = StreamArchiveCollector(settings.stream_archive_max_bytes)
    for chunk in chunks:
        collector.add(chunk)
    return collector.payload()


def _extract_sse_message_content(raw_content: str) -> str:
    parts: list[str] = []
    normalized_content = raw_content.replace("\\r\\n", "\n").replace("\\n", "\n")
    for line in normalized_content.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list):
            continue
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                parts.append(delta["content"])
            message = choice.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                parts.append(message["content"])
    return "".join(parts)


def _write_chat_archive(
    request: Request,
    original_body: Any,
    relayed_body: Any,
    response_body: Any,
    scan_result: AggregatedScanResult | None,
    action_taken: str,
    is_stream: bool,
    started_at: float,
    identity: RequestIdentity | None = None,
) -> None:
    if not isinstance(original_body, dict):
        return
    request_id = getattr(request.state, "request_id", "") or uuid4().hex
    matched_rule_ids = [result.rule_id for result in scan_result.results if result.hit and result.rule_id] if scan_result else []
    block_result = scan_result.block_result if scan_result else None
    payload = ArchivePayload(
        request_id=request_id,
        user_id=identity.user_id if identity else "",
        api_key_id=identity.api_key_id if identity else "",
        model=original_body.get("model", ""),
        capability="chat",
        prompt_original=original_body.get("messages", []),
        prompt_desensitized=relayed_body.get("messages", []) if isinstance(relayed_body, dict) else original_body.get("messages", []),
        response=response_body,
        is_stream=is_stream,
        is_blocked=action_taken == "blocked",
        is_desensitized=action_taken == "desensitized",
        action_taken=action_taken,
        blocked_rule_id=block_result.rule_id if block_result else "",
        matched_rule_ids=matched_rule_ids,
        latency_ms=int((perf_counter() - started_at) * 1000),
    )
    archive_queue = getattr(request.app.state, "archive_queue", None)
    if archive_queue is not None and archive_queue.enqueue_archive(payload):
        return
    writer = getattr(request.app.state, "training_writer", None)
    if writer is None:
        return
    asyncio.create_task(_safe_write_training(writer, payload))


async def _write_image_archive(
    request: Request,
    original_body: Any,
    response: Response | StreamingResponse,
    started_at: float,
    identity: RequestIdentity | None = None,
) -> None:
    if not isinstance(original_body, dict) or isinstance(response, StreamingResponse):
        return
    request_id = getattr(request.state, "request_id", "") or uuid4().hex
    response_payload = _parse_response_json(response)
    await _schedule_image_asset_archive(request, request_id, response_payload)


def _parse_response_json(response: Response) -> Any:
    content = response.body.decode("utf-8", errors="replace") if isinstance(response.body, bytes) else response.body
    try:
        return json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None


def _extract_image_response_references(payload: Any) -> dict[str, Any]:
    urls: list[str] = []
    b64_count = 0
    asset_sources: list[str] = []
    assets = extract_image_asset_sources(payload)
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("url"), str):
                urls.append(item["url"])
            if isinstance(item.get("b64_json"), str) and item["b64_json"]:
                b64_count += 1
    for asset in assets:
        asset_sources.append(asset.source_type)
    return {"urls": urls, "b64_count": b64_count, "assets": assets, "asset_sources": asset_sources}


async def _schedule_image_asset_archive(request: Request, request_id: str, response_payload: Any) -> None:
    if not request_id or not extract_image_asset_sources(response_payload):
        return
    archiver = getattr(request.app.state, "image_asset_archiver", None)
    if archiver is None:
        archiver = ImageAssetArchiver()
    if getattr(request.app.state, "image_asset_archive_inline", False):
        await archiver.archive_response(request_id, response_payload)
        return
    task = asyncio.create_task(archiver.archive_response(request_id, response_payload))
    tasks = getattr(request.app.state, "image_asset_archive_tasks", None)
    if tasks is None:
        tasks = set()
        request.app.state.image_asset_archive_tasks = tasks
    tasks.add(task)
    task.add_done_callback(tasks.discard)


def _write_chat_audit(
    request: Request,
    scan_result: AggregatedScanResult | None,
    scanned_text: str,
    action_taken: str,
    identity: RequestIdentity | None = None,
    desensitized_text: str = "",
) -> None:
    if scan_result is None or not scan_result.hit:
        return
    payload = AuditPayload(
        request_id=getattr(request.state, "request_id", ""),
        scan_result=scan_result,
        action_taken=action_taken,
        user_id=identity.user_id if identity else getattr(getattr(request.state, "identity", None), "user_id", ""),
        scanned_text=scanned_text,
        desensitized_text=desensitized_text,
    )
    archive_queue = getattr(request.app.state, "archive_queue", None)
    if archive_queue is not None and archive_queue.enqueue_audit(payload):
        return
    writer = getattr(request.app.state, "audit_writer", None)
    if writer is None:
        return
    asyncio.create_task(_safe_write_audit(writer, payload))


async def _safe_write_training(writer: TrainingConversationWriter, payload: ArchivePayload) -> None:
    try:
        await writer.write_from_archive_payload(payload)
    except Exception:
        return


async def _safe_write_audit(writer: AuditWriter, payload: AuditPayload) -> None:
    try:
        await writer.write_scan_result(payload)
    except Exception:
        return


async def _read_request_body(request: Request, path: str) -> tuple[Any, bytes]:
    if request.method not in JSON_BODY_METHODS:
        return None, b""
    try:
        raw_body = await request.body()
    except ClientDisconnect as exc:
        raise HTTPException(status_code=499, detail="client disconnected while sending request body") from exc
    if not raw_body:
        return None, raw_body
    content_type = request.headers.get("content-type", "")
    is_known_endpoint = path in KNOWN_JSON_ENDPOINTS
    should_parse_json = is_known_endpoint or "application/json" in content_type.lower()
    if not should_parse_json:
        return None, raw_body
    try:
        body = await request.json()
    except Exception as exc:
        if is_known_endpoint:
            raise HTTPException(status_code=400, detail="invalid json body") from exc
        # 未知 JSON 端点解析失败时降级为字节透传，避免拒绝合法但非严格 JSON 的请求。
        return None, raw_body
    if is_known_endpoint and not isinstance(body, dict):
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
BLOCK_SCAN_ROLES = {"user", "tool", "function"}
DESENSITIZE_ROLES = {"user", "tool", "function"}


def desensitize_chat_request_body(body: dict[str, Any]) -> dict[str, Any]:
    sanitized_body = deepcopy(body)
    messages = sanitized_body.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict) or message.get("role") not in DESENSITIZE_ROLES:
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


def extract_latest_text_from_request(path: str, body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    if path == CHAT_COMPLETIONS_PATH:
        return extract_latest_text_from_messages(body.get("messages", []))
    return extract_text_from_request(path, body)


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


def extract_latest_text_from_messages(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") not in BLOCK_SCAN_ROLES:
            continue
        text = "\n".join(part for part in _extract_content_parts(message.get("content")) if part)
        if text:
            return text
    return ""


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
