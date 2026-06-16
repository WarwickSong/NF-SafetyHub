import asyncio

import pytest
from fastapi import FastAPI

from proxy.relay import _schedule_image_asset_archive


@pytest.mark.asyncio
async def test_schedule_image_asset_archive_keeps_raw_payload_and_tracks_task():
    calls = []
    payload = {"data": [{"b64_json": "raw-b64"}]}

    class FakeImageAssetArchiver:
        async def archive_response(self, request_id, response_payload):
            calls.append((request_id, response_payload))

    app = FastAPI()
    app.state.image_asset_archiver = FakeImageAssetArchiver()

    class Request:
        pass

    request = Request()
    request.app = app

    await _schedule_image_asset_archive(request, "req_image", payload)
    tasks = getattr(app.state, "image_asset_archive_tasks")
    await asyncio.gather(*list(tasks))

    assert calls == [("req_image", payload)]
    assert calls[0][1]["data"][0]["b64_json"] == "raw-b64"
