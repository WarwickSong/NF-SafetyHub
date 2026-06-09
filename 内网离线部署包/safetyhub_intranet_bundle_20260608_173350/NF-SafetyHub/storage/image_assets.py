import base64
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import hashlib
import ipaddress
from pathlib import Path
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import settings
from storage.database import get_session_factory
from storage.models import ImageAsset, utc_now


@dataclass(slots=True)
class ImageAssetSource:
    index: int
    source_type: str
    url: str = ""
    b64_json: str = ""


class ImageAssetArchiver:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None,
        asset_dir: str | Path | None = None,
        max_size_bytes: int | None = None,
        timeout_seconds: int | None = None,
    ):
        self._session_factory = session_factory or get_session_factory()
        self._asset_dir = Path(asset_dir or settings.image_asset_dir)
        self._max_size_bytes = max_size_bytes or settings.image_asset_max_size_mb * 1024 * 1024
        self._timeout_seconds = timeout_seconds or settings.image_asset_download_timeout_seconds

    async def archive_response(self, request_id: str, response_payload: Any) -> None:
        sources = extract_image_asset_sources(response_payload)
        if not request_id or not sources:
            return
        for source in sources:
            try:
                await self._archive_source(request_id, source)
            except Exception as exc:
                await self._record_asset(
                    request_id=request_id,
                    source=source,
                    status="failed",
                    error=str(exc)[:1000],
                )

    async def _archive_source(self, request_id: str, source: ImageAssetSource) -> None:
        if source.source_type == "b64_json":
            content = _decode_b64(source.b64_json)
            mime_type = _detect_mime_type(content)
        elif source.source_type == "url":
            content, mime_type = await self._download_url(source.url)
        else:
            raise ValueError("unsupported image asset source")
        if len(content) > self._max_size_bytes:
            raise ValueError("image asset exceeds max size")
        file_hash = hashlib.sha256(content).hexdigest()
        extension = _extension_for_mime_type(mime_type)
        relative_path = Path(request_id) / f"{source.index}_{file_hash[:16]}{extension}"
        target_path = self._asset_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        display_path = str(relative_path).replace("\\", "/")
        await self._record_asset(
            request_id=request_id,
            source=source,
            status="completed",
            local_path=display_path,
            sha256=file_hash,
            mime_type=mime_type,
            size_bytes=len(content),
            completed_at=utc_now(),
        )

    async def _download_url(self, url: str) -> tuple[bytes, str]:
        _validate_public_image_url(url)
        timeout = httpx.Timeout(self._timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await _get_with_safe_redirects(client, url)
        if response.status_code >= 400:
            raise ValueError(f"image asset download failed with status {response.status_code}")
        content = response.content
        if len(content) > self._max_size_bytes:
            raise ValueError("image asset exceeds max size")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        mime_type = content_type or _detect_mime_type(content)
        if not mime_type.startswith("image/"):
            raise ValueError("downloaded asset is not an image")
        return content, mime_type

    async def _record_asset(
        self,
        request_id: str,
        source: ImageAssetSource,
        status: str,
        local_path: str = "",
        sha256: str = "",
        mime_type: str = "",
        size_bytes: int = 0,
        error: str = "",
        completed_at: datetime | None = None,
    ) -> ImageAsset:
        async with self._session_factory() as session:
            asset = ImageAsset(
                request_id=request_id,
                source_index=source.index,
                source_type=source.source_type,
                source_url=source.url,
                status=status,
                local_path=local_path,
                sha256=sha256,
                mime_type=mime_type,
                size_bytes=size_bytes,
                error=error,
                completed_at=completed_at,
            )
            session.add(asset)
            await session.commit()
            await session.refresh(asset)
            return asset


class ImageAssetReader:
    def __init__(self, session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory or get_session_factory()

    async def list(self, request_id: str | None = None, limit: int = 20, offset: int = 0) -> list[ImageAsset]:
        safe_limit = min(max(limit, 1), 100)
        safe_offset = max(offset, 0)
        stmt = select(ImageAsset).order_by(ImageAsset.created_at.desc(), ImageAsset.id.desc()).limit(safe_limit).offset(safe_offset)
        if request_id:
            stmt = stmt.where(ImageAsset.request_id == request_id)
        async with self._session_factory() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get(self, asset_id: int) -> ImageAsset | None:
        async with self._session_factory() as session:
            return await session.get(ImageAsset, asset_id)


def extract_image_asset_sources(payload: Any) -> list[ImageAssetSource]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []
    sources: list[ImageAssetSource] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if isinstance(url, str) and url:
            sources.append(ImageAssetSource(index=index, source_type="url", url=url))
        b64_json = item.get("b64_json")
        if isinstance(b64_json, str) and b64_json:
            sources.append(ImageAssetSource(index=index, source_type="b64_json", b64_json=b64_json))
    return sources


def sanitize_image_response_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    sanitized = dict(payload)
    data = payload.get("data")
    if not isinstance(data, list):
        return sanitized
    sanitized_data = []
    for item in data:
        if not isinstance(item, dict):
            sanitized_data.append(item)
            continue
        sanitized_item = dict(item)
        if isinstance(sanitized_item.get("b64_json"), str) and sanitized_item["b64_json"]:
            sanitized_item["b64_json"] = "[archived:image_b64]"
        sanitized_data.append(sanitized_item)
    sanitized["data"] = sanitized_data
    return sanitized


async def _get_with_safe_redirects(client: httpx.AsyncClient, url: str) -> httpx.Response:
    current_url = url
    for _ in range(5):
        _validate_public_image_url(current_url)
        response = await client.get(current_url)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        redirect_url = response.headers.get("location", "")
        if not redirect_url:
            raise ValueError("image asset redirect missing location")
        current_url = str(httpx.URL(current_url).join(redirect_url))
    raise ValueError("image asset redirect limit exceeded")


def _validate_public_image_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("unsupported image asset url scheme")
    if not parsed.hostname:
        raise ValueError("image asset url host is required")
    _validate_public_host(parsed.hostname)


def _validate_public_host(hostname: str) -> None:
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None
    if ip is not None:
        _validate_public_ip(ip)
        return
    try:
        addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("image asset url host cannot be resolved") from exc
    for address in addresses:
        _validate_public_ip(ipaddress.ip_address(address[4][0]))


def _validate_public_ip(ip: ipaddress._BaseAddress) -> None:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        raise ValueError("image asset url host is not public")


def _decode_b64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ValueError("invalid b64 image asset") from exc


def _detect_mime_type(content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _extension_for_mime_type(mime_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }.get(mime_type, ".bin")
