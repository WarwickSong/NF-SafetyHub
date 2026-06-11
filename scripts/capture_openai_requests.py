from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key", "proxy-authorization"}
LOG_PATH: Path | None = None

app = FastAPI(title="OpenAI Request Capture", version="0.1.0")


def sanitize_headers(headers: dict[str, str]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for name, value in headers.items():
        normalized = name.lower()
        if normalized in SENSITIVE_HEADERS:
            sanitized[name] = redact_secret(value)
        else:
            sanitized[name] = value
    return sanitized


def redact_secret(value: str) -> dict[str, str | int]:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    if len(value) <= 12:
        preview = "***"
    else:
        preview = f"{value[:8]}...{value[-4:]}"
    return {"redacted": preview, "sha256": digest, "length": len(value)}


async def capture_request(request: Request) -> dict[str, Any]:
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8", errors="replace")
    parsed_body: Any = None
    parse_error = ""
    if body_text:
        try:
            parsed_body = json.loads(body_text)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
    record = {
        "capture_id": uuid.uuid4().hex,
        "ts": time.time(),
        "client": request.client.host if request.client else "",
        "method": request.method,
        "path": request.url.path,
        "query": str(request.url.query),
        "headers": sanitize_headers(dict(request.headers)),
        "body_text": body_text,
        "body_json": parsed_body,
        "body_json_error": parse_error,
        "body_bytes": len(body_bytes),
    }
    await append_record(record)
    return record


async def append_record(record: dict[str, Any]) -> None:
    print(
        f"capture {record['capture_id']} {record['method']} {record['path']} bytes={record['body_bytes']}",
        flush=True,
    )
    if LOG_PATH is None:
        return
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    await asyncio.to_thread(write_line, LOG_PATH, line)


def write_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(line)


def model_name(record: dict[str, Any], fallback: str = "capture-model") -> str:
    body = record.get("body_json")
    if isinstance(body, dict) and isinstance(body.get("model"), str):
        return body["model"]
    return fallback


def wants_stream(record: dict[str, Any]) -> bool:
    body = record.get("body_json")
    return isinstance(body, dict) and bool(body.get("stream"))


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    await capture_request(request)
    return {"status": "ok"}


@app.get("/v1/models")
@app.get("/models")
async def list_models(request: Request) -> JSONResponse:
    await capture_request(request)
    return JSONResponse({"object": "list", "data": [{"id": "deepseek-v4-pro", "object": "model", "owned_by": "capture"}]})


@app.api_route("/v1/chat/completions", methods=["POST", "OPTIONS"])
@app.api_route("/chat/completions", methods=["POST", "OPTIONS"])
@app.api_route("/v1/completions", methods=["POST", "OPTIONS"])
@app.api_route("/completions", methods=["POST", "OPTIONS"])
async def chat_completions(request: Request):
    record = await capture_request(request)
    if request.method == "OPTIONS":
        return JSONResponse({"ok": True, "capture_id": record["capture_id"]})
    if wants_stream(record):
        return StreamingResponse(stream_chat_response(record), media_type="text/event-stream")
    return JSONResponse(chat_response(record))


@app.api_route("/v1/responses", methods=["POST", "OPTIONS"])
@app.api_route("/responses", methods=["POST", "OPTIONS"])
async def responses(request: Request):
    record = await capture_request(request)
    if request.method == "OPTIONS":
        return JSONResponse({"ok": True, "capture_id": record["capture_id"]})
    if wants_stream(record):
        return StreamingResponse(stream_response_api(record), media_type="text/event-stream")
    return JSONResponse({
        "id": f"resp_{record['capture_id']}",
        "object": "response",
        "created_at": int(record["ts"]),
        "model": model_name(record),
        "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "capture ok"}]}],
    })


@app.api_route("/v1/messages", methods=["POST", "OPTIONS"])
@app.api_route("/messages", methods=["POST", "OPTIONS"])
async def messages(request: Request):
    record = await capture_request(request)
    if request.method == "OPTIONS":
        return JSONResponse({"ok": True, "capture_id": record["capture_id"]})
    if wants_stream(record):
        return StreamingResponse(stream_anthropic_messages(record), media_type="text/event-stream")
    return JSONResponse({
        "id": f"msg_{record['capture_id']}",
        "type": "message",
        "role": "assistant",
        "model": model_name(record),
        "content": [{"type": "text", "text": "capture ok"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 2},
    })


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def catch_all(request: Request, path: str):
    record = await capture_request(request)
    if request.method == "OPTIONS":
        return JSONResponse({"ok": True, "capture_id": record["capture_id"], "path": f"/{path}"})
    if request.method == "POST":
        if wants_stream(record):
            return StreamingResponse(stream_chat_response(record), media_type="text/event-stream")
        return JSONResponse(chat_response(record))
    return JSONResponse({"ok": True, "capture_id": record["capture_id"], "path": f"/{path}", "content": "capture ok"})


def chat_response(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{record['capture_id']}",
        "object": "chat.completion",
        "created": int(record["ts"]),
        "model": model_name(record),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "capture ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    }


async def stream_chat_response(record: dict[str, Any]):
    model = model_name(record)
    response_id = f"chatcmpl-{record['capture_id']}"
    created = int(record["ts"])
    chunks = [
        {"id": response_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
        {"id": response_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [{"index": 0, "delta": {"content": "capture ok"}, "finish_reason": None}]},
        {"id": response_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    ]
    for chunk in chunks:
        yield f"data: {json.dumps(chunk, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")
        await asyncio.sleep(0.01)
    yield b"data: [DONE]\n\n"


async def stream_response_api(record: dict[str, Any]):
    response_id = f"resp_{record['capture_id']}"
    events = [
        {"type": "response.created", "response": {"id": response_id, "model": model_name(record)}},
        {"type": "response.output_text.delta", "delta": "capture ok"},
        {"type": "response.completed", "response": {"id": response_id, "status": "completed"}},
    ]
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")
        await asyncio.sleep(0.01)
    yield b"data: [DONE]\n\n"


async def stream_anthropic_messages(record: dict[str, Any]):
    message_id = f"msg_{record['capture_id']}"
    events = [
        ("message_start", {"type": "message_start", "message": {"id": message_id, "type": "message", "role": "assistant", "model": model_name(record), "content": [], "stop_reason": None}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "capture ok"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_stop", {"type": "message_stop"}),
    ]
    for event_name, payload in events:
        yield f"event: {event_name}\n".encode("utf-8")
        yield f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")
        await asyncio.sleep(0.01)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture OpenAI-compatible client requests")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--log-file", default="data/capture/openai_requests.ndjson")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    global LOG_PATH
    LOG_PATH = Path(args.log_file).resolve()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
