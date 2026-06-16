import json

import pytest
from fastapi.responses import JSONResponse, StreamingResponse

from engine.models import AggregatedScanResult, ScannerResult
from proxy.fake_response import generate_fake_response


@pytest.mark.asyncio
async def test_generate_fake_response_returns_openai_compatible_json():
    scan_result = AggregatedScanResult(results=[ScannerResult(hit=True, level="block", rule_id="KW-001")])

    response = await generate_fake_response({"model": "gpt-test"}, scan_result, is_stream=False)

    assert isinstance(response, JSONResponse)
    payload = json.loads(response.body)
    assert payload["object"] == "chat.completion"
    assert payload["model"] == "gpt-test"
    assert payload["choices"][0]["message"]["role"] == "assistant"
    assert payload["choices"][0]["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_generate_fake_response_returns_streaming_response():
    scan_result = ScannerResult(hit=True, level="block", rule_id="KW-001")

    response = await generate_fake_response({"model": "gpt-test"}, scan_result, is_stream=True)

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"
