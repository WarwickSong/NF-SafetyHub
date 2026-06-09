from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.router import router
from config import Settings
from storage.models import ImageAsset


class FakeImageAssetReader:
    async def list(self, request_id=None, limit=20, offset=0):
        return [
            ImageAsset(
                id=1,
                request_id=request_id or "req_image",
                source_index=0,
                source_type="b64_json",
                status="completed",
                local_path="req_image/0_test.png",
                sha256="a" * 64,
                mime_type="image/png",
                size_bytes=18,
                created_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
        ]


class FakeAdminOperationWriter:
    def __init__(self):
        self.operations = []

    async def write(self, payload):
        self.operations.append(payload)


def test_admin_image_assets_list_requires_auth_and_records_operation():
    app = FastAPI()
    app.include_router(router, prefix="/admin/api")
    app.state.settings = Settings(admin_password="strong-local-password")
    app.state.image_asset_reader = FakeImageAssetReader()
    operation_writer = FakeAdminOperationWriter()
    app.state.admin_operation_writer = operation_writer

    with TestClient(app) as client:
        unauthenticated_response = client.get("/admin/api/image-assets?request_id=req_image")
        authenticated_response = client.get(
            "/admin/api/image-assets?request_id=req_image",
            auth=("admin", "strong-local-password"),
        )

    assert unauthenticated_response.status_code == 401
    assert authenticated_response.status_code == 200
    payload = authenticated_response.json()
    assert payload["items"][0]["request_id"] == "req_image"
    assert payload["items"][0]["status"] == "completed"
    assert operation_writer.operations[0].operation == "image_asset.list"
    assert operation_writer.operations[0].resource_id == "req_image"
