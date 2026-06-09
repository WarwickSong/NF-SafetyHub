from collections.abc import AsyncGenerator
import json
import time
import uuid

from fastapi.responses import JSONResponse, StreamingResponse

from engine.models import AggregatedScanResult, ScannerResult

TEMPLATES = {
    "block": "抱歉，我无法处理您的请求。您输入的内容可能包含敏感信息，请检查后重试。如需帮助，请联系信息安全团队。",
    "warn": "请注意，您输入的内容可能包含敏感信息，请检查后重试。",
}


async def generate_fake_response(
    request_body: dict,
    scan_result: AggregatedScanResult | ScannerResult,
    is_stream: bool,
) -> JSONResponse | StreamingResponse:
    result = _select_result(scan_result)
    template = TEMPLATES.get(result.level, TEMPLATES["block"])
    model = request_body.get("model", "gpt-3.5-turbo")
    if is_stream:
        return StreamingResponse(_stream_fake_chunks(template, model), media_type="text/event-stream")
    return JSONResponse(_build_non_stream_response(template, model))


def _select_result(scan_result: AggregatedScanResult | ScannerResult) -> ScannerResult:
    if isinstance(scan_result, ScannerResult):
        return scan_result
    return scan_result.block_result or (scan_result.results[0] if scan_result.results else ScannerResult(hit=False))


def _build_non_stream_response(content: str, model: str) -> dict:
    return {
        "id": f"chatcmpl-safetyhub-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def _stream_fake_chunks(content: str, model: str) -> AsyncGenerator[str, None]:
    response_id = f"chatcmpl-safetyhub-{uuid.uuid4().hex[:8]}"
    created = int(time.time())
    for index in range(0, len(content), 2):
        delta = content[index:index + 2]
        payload = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    final_payload = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final_payload, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
