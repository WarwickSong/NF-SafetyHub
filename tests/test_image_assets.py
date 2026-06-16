import base64
import socket

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from storage.image_assets import ImageAssetArchiver, extract_image_asset_sources, sanitize_image_response_payload
from storage.models import Base, ImageAsset


@pytest.mark.asyncio
async def test_image_asset_archiver_saves_b64_image(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    archiver = ImageAssetArchiver(session_factory=session_factory, asset_dir=tmp_path)
    b64_image = base64.b64encode(b"\x89PNG\r\n\x1a\nimage-bytes").decode("ascii")

    await archiver.archive_response("req_image_1", {"data": [{"b64_json": b64_image}]})

    async with session_factory() as session:
        asset = await session.scalar(select(ImageAsset).where(ImageAsset.request_id == "req_image_1"))

    assert asset is not None
    assert asset.status == "completed"
    assert asset.source_type == "b64_json"
    assert asset.mime_type == "image/png"
    assert asset.size_bytes == len(b"\x89PNG\r\n\x1a\nimage-bytes")
    assert asset.sha256
    assert (tmp_path / asset.local_path).exists()

    await engine.dispose()


@pytest.mark.asyncio
async def test_image_asset_archiver_downloads_url_image(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    archiver = ImageAssetArchiver(session_factory=session_factory, asset_dir=tmp_path)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\xff\xd8\xffimage-bytes", headers={"content-type": "image/jpeg"})

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))])

    await archiver.archive_response("req_image_2", {"data": [{"url": "https://cdn.example.com/image.jpg"}]})

    async with session_factory() as session:
        asset = await session.scalar(select(ImageAsset).where(ImageAsset.request_id == "req_image_2"))

    assert asset is not None
    assert asset.status == "completed"
    assert asset.source_type == "url"
    assert asset.source_url == "https://cdn.example.com/image.jpg"
    assert asset.mime_type == "image/jpeg"
    assert (tmp_path / asset.local_path).exists()

    await engine.dispose()


@pytest.mark.asyncio
async def test_image_asset_archiver_records_failure_without_raising(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    archiver = ImageAssetArchiver(session_factory=session_factory, asset_dir=tmp_path)

    await archiver.archive_response("req_image_3", {"data": [{"b64_json": "not-valid-base64"}]})

    async with session_factory() as session:
        asset = await session.scalar(select(ImageAsset).where(ImageAsset.request_id == "req_image_3"))

    assert asset is not None
    assert asset.status == "failed"
    assert asset.source_type == "b64_json"
    assert "invalid b64 image asset" in asset.error
    assert asset.local_path == ""

    await engine.dispose()


@pytest.mark.asyncio
async def test_image_asset_archiver_rejects_private_redirect_target(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    archiver = ImageAssetArchiver(session_factory=session_factory, asset_dir=tmp_path)

    async def handler(request: httpx.Request) -> httpx.Response:
        if "cdn.example.com" in str(request.url):
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private.png"})
        return httpx.Response(200, content=b"\x89PNG\r\n\x1a\nimage-bytes", headers={"content-type": "image/png"})

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def build_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build_client)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))])

    await archiver.archive_response("req_image_private", {"data": [{"url": "https://cdn.example.com/image.jpg"}]})

    async with session_factory() as session:
        asset = await session.scalar(select(ImageAsset).where(ImageAsset.request_id == "req_image_private"))

    assert asset is not None
    assert asset.status == "failed"
    assert "not public" in asset.error

    await engine.dispose()


def test_extract_and_sanitize_image_response_payload():
    payload = {
        "data": [
            {"url": "https://cdn.example.com/image.png"},
            {"b64_json": base64.b64encode(b"image").decode("ascii")},
        ]
    }

    sources = extract_image_asset_sources(payload)
    sanitized = sanitize_image_response_payload(payload)

    assert [source.source_type for source in sources] == ["url", "b64_json"]
    assert sanitized["data"][0]["url"] == "https://cdn.example.com/image.png"
    assert sanitized["data"][1]["b64_json"] == "[archived:image_b64]"
    assert payload["data"][1]["b64_json"] != "[archived:image_b64]"
