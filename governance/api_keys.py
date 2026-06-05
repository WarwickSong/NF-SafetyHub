from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import base64
import csv
import hashlib
import io
import os
import secrets
import uuid
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import settings
from governance.key_provider import KeyCreateParams, KeyProvider, KeyProviderError
from storage.database import get_session_factory
from storage.models import ApiKeyRecord, utc_now


@dataclass(slots=True)
class ApiKeyCreate:
    name: str
    owner_user_id: str
    upstream_key: str = ""
    reuse_upstream_key: bool = True
    expires_at: datetime | None = None
    provider_name: str = "passthrough"
    owner_department: str | None = None
    cost_center: str | None = None
    create_mode: str = "manual"
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class ApiKeyCreateResult:
    record: ApiKeyRecord
    safetyhub_key: str | None = None


@dataclass(slots=True)
class ApiKeyUpdate:
    name: str | None = None
    owner_user_id: str | None = None
    owner_department: str | None = None
    cost_center: str | None = None
    expires_at: datetime | None = None


@dataclass(slots=True)
class ApiKeyPage:
    items: list[ApiKeyRecord]
    total: int
    limit: int
    offset: int


@dataclass(slots=True)
class BulkReplaceRow:
    identifier: str
    new_upstream_key: str


@dataclass(slots=True)
class BulkReplaceResult:
    identifier: str
    status: str
    message: str
    api_key_id: str = ""


class ApiKeyCrypto:
    def __init__(self, data_key: str | None = None):
        self._data_key = data_key or os.getenv(settings.data_encryption_key_env) or _development_data_key()
        self._fernet = Fernet(_fernet_key(self._data_key))

    def encrypt(self, value: str) -> str:
        token = self._fernet.encrypt(value.encode("utf-8")).decode("ascii")
        return f"v2:{token}"

    def decrypt(self, value: str) -> str:
        if not value.startswith("v2:"):
            raise ValueError("unsupported encrypted value version")
        token = value.removeprefix("v2:").encode("ascii")
        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise ValueError("invalid encrypted value") from exc


class ApiKeyService:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None,
        crypto: ApiKeyCrypto | None = None,
        key_provider: KeyProvider | None = None,
    ):
        self._session_factory = session_factory or get_session_factory()
        self._crypto = crypto or ApiKeyCrypto()
        self._key_provider = key_provider

    async def create_ksync(self, payload: ApiKeyCreate) -> ApiKeyRecord:
        result = await self.create(payload)
        return result.record

    async def create(self, payload: ApiKeyCreate) -> ApiKeyCreateResult:
        if payload.create_mode == "provider":
            return await self.create_from_provider(payload)
        upstream_key = payload.upstream_key.strip()
        _validate_key(upstream_key)
        return await self._create_record(payload, upstream_key, upstream_key if payload.reuse_upstream_key else None, None, None if payload.reuse_upstream_key else True)

    async def create_from_provider(self, payload: ApiKeyCreate) -> ApiKeyCreateResult:
        if self._key_provider is None:
            raise ValueError("key provider is not configured")
        upstream_info = await self._key_provider.create_key(
            KeyCreateParams(
                name=payload.name.strip(),
                owner_user_id=payload.owner_user_id.strip(),
                expires_at=payload.expires_at,
                metadata=payload.metadata or {},
            )
        )
        if not upstream_info.key_secret:
            raise ValueError("key provider did not return upstream key secret")
        _validate_key(upstream_info.key_secret)
        provider_payload = ApiKeyCreate(
            name=payload.name,
            owner_user_id=payload.owner_user_id,
            upstream_key=upstream_info.key_secret,
            reuse_upstream_key=payload.reuse_upstream_key,
            expires_at=payload.expires_at,
            provider_name=self._key_provider.provider_name,
            owner_department=payload.owner_department,
            cost_center=payload.cost_center,
            create_mode="manual",
            metadata=payload.metadata,
        )
        try:
            return await self._create_record(provider_payload, upstream_info.key_secret, upstream_info.key_secret if payload.reuse_upstream_key else None, upstream_info.key_id, True)
        except Exception:
            if upstream_info.key_id:
                await self._key_provider.revoke_key(upstream_info.key_id)
            raise

    async def _create_record(
        self,
        payload: ApiKeyCreate,
        upstream_key: str,
        safetyhub_key: str | None,
        upstream_key_id: str | None,
        reveal_safetyhub_key: bool | None,
    ) -> ApiKeyCreateResult:
        async with self._session_factory() as session:
            actual_safetyhub_key = safetyhub_key or await self._generate_unique_safetyhub_key(session)
            record = _build_api_key_record(
                payload,
                upstream_key,
                actual_safetyhub_key,
                self._crypto.encrypt(upstream_key),
                self._crypto.encrypt(actual_safetyhub_key),
                upstream_key_id,
            )
            existing = await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.key_hash == record.key_hash))
            if existing is not None:
                raise ValueError("safetyhub api key already exists")
            session.add(record)
            await session.commit()
            await session.refresh(record)
            if reveal_safetyhub_key is None:
                reveal_safetyhub_key = not payload.reuse_upstream_key
            return ApiKeyCreateResult(record=record, safetyhub_key=actual_safetyhub_key if reveal_safetyhub_key else None)

    async def _generate_unique_safetyhub_key(self, session: AsyncSession) -> str:
        for _ in range(10):
            safetyhub_key = f"sk-sh-{secrets.token_urlsafe(32)}"
            existing = await session.scalar(select(ApiKeyRecord.id).where(ApiKeyRecord.key_hash == hash_api_key(safetyhub_key)))
            if existing is None:
                return safetyhub_key
        raise ValueError("failed to generate unique safetyhub api key")

    async def list(self, limit: int = 20, offset: int = 0, status: str | None = None) -> ApiKeyPage:
        safe_limit = min(max(limit, 1), 100)
        safe_offset = max(offset, 0)
        stmt = select(ApiKeyRecord)
        count_stmt = select(func.count(ApiKeyRecord.id))
        if status:
            stmt = stmt.where(ApiKeyRecord.status == status)
            count_stmt = count_stmt.where(ApiKeyRecord.status == status)
        stmt = stmt.order_by(ApiKeyRecord.created_at.desc()).limit(safe_limit).offset(safe_offset)
        async with self._session_factory() as session:
            total = await session.scalar(count_stmt)
            result = await session.execute(stmt)
            return ApiKeyPage(items=list(result.scalars().all()), total=total or 0, limit=safe_limit, offset=safe_offset)

    async def count(self) -> int:
        async with self._session_factory() as session:
            return await session.scalar(select(func.count(ApiKeyRecord.id))) or 0

    async def get(self, api_key_id: str) -> ApiKeyRecord | None:
        async with self._session_factory() as session:
            return await session.get(ApiKeyRecord, api_key_id)

    async def find_by_raw_key(self, raw_key: str) -> ApiKeyRecord | None:
        async with self._session_factory() as session:
            return await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.key_hash == hash_api_key(raw_key)))

    async def revoke(self, api_key_id: str) -> ApiKeyRecord | None:
        async with self._session_factory() as session:
            record = await session.get(ApiKeyRecord, api_key_id)
            if record is None:
                return None
            should_revoke_upstream = self._key_provider is not None and record.provider_name == self._key_provider.provider_name and bool(record.upstream_key_id)
            upstream_key_id = record.upstream_key_id or ""
        if should_revoke_upstream:
            await self._key_provider.revoke_key(upstream_key_id)
        async with self._session_factory() as session:
            record = await session.get(ApiKeyRecord, api_key_id)
            if record is None:
                return None
            record.status = "revoked"
            record.revoked_at = utc_now()
            await session.commit()
            await session.refresh(record)
            return record

    async def delete_revoked(self, api_key_id: str) -> bool | None:
        async with self._session_factory() as session:
            record = await session.get(ApiKeyRecord, api_key_id)
            if record is None:
                return None
            if record.status != "revoked":
                raise ValueError("only revoked api key can be deleted")
            await session.execute(delete(ApiKeyRecord).where(ApiKeyRecord.id == api_key_id))
            await session.commit()
            return True

    async def update(self, api_key_id: str, fields: dict[str, Any]) -> ApiKeyRecord | None:
        if not fields:
            return await self.get(api_key_id)
        allowed = {"name", "owner_user_id", "owner_department", "cost_center", "expires_at"}
        async with self._session_factory() as session:
            record = await session.get(ApiKeyRecord, api_key_id)
            if record is None:
                return None
            for field_name, value in fields.items():
                if field_name not in allowed:
                    continue
                if field_name in {"name", "owner_user_id"}:
                    if value is None:
                        continue
                    stripped = str(value).strip()
                    if not stripped:
                        continue
                    setattr(record, field_name, stripped)
                else:
                    setattr(record, field_name, value)
            await session.commit()
            await session.refresh(record)
            return record

    async def replace_upstream_key(self, api_key_id: str, new_upstream_key: str) -> ApiKeyRecord | None:
        raw_key = new_upstream_key.strip()
        _validate_key(raw_key)
        async with self._session_factory() as session:
            record = await session.get(ApiKeyRecord, api_key_id)
            if record is None:
                return None
            record.upstream_key_encrypted = self._crypto.encrypt(raw_key)
            record.upstream_key_prefix = key_prefix(raw_key)
            record.is_decoupled = True
            await session.commit()
            await session.refresh(record)
            return record

    async def bulk_replace(self, rows: list[BulkReplaceRow]) -> list[BulkReplaceResult]:
        results: list[BulkReplaceResult] = []
        for row in rows:
            record = await self._find_for_bulk_replace(row.identifier)
            if record is None:
                results.append(BulkReplaceResult(identifier=row.identifier, status="failed", message="未找到匹配 APIKey"))
                continue
            try:
                updated = await self.replace_upstream_key(record.id, row.new_upstream_key)
            except ValueError as exc:
                results.append(BulkReplaceResult(identifier=row.identifier, status="failed", message=str(exc), api_key_id=record.id))
                continue
            results.append(BulkReplaceResult(identifier=row.identifier, status="success", message="已替换", api_key_id=updated.id if updated else record.id))
        return results

    async def decrypt_upstream_key(self, record: ApiKeyRecord) -> str:
        if not record.upstream_key_encrypted:
            return ""
        return self._crypto.decrypt(record.upstream_key_encrypted)

    async def decrypt_safetyhub_key(self, record: ApiKeyRecord) -> str:
        if not record.safetyhub_key_encrypted:
            return ""
        return self._crypto.decrypt(record.safetyhub_key_encrypted)

    async def reveal_safetyhub_key(self, api_key_id: str) -> str | None:
        record = await self.get(api_key_id)
        if record is None:
            return None
        return await self.decrypt_safetyhub_key(record)

    async def _find_for_bulk_replace(self, identifier: str) -> ApiKeyRecord | None:
        value = identifier.strip()
        if not value:
            return None
        async with self._session_factory() as session:
            record = await session.get(ApiKeyRecord, value)
            if record is not None:
                return record
            if value.startswith("sk-"):
                record = await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.key_hash == hash_api_key(value)))
                if record is not None:
                    return record
            stmt = select(ApiKeyRecord).where(ApiKeyRecord.key_prefix == value)
            result = await session.execute(stmt)
            matches = list(result.scalars().all())
            if len(matches) == 1:
                return matches[0]
            return None


def parse_bulk_replace_csv(csv_content: str) -> list[BulkReplaceRow]:
    rows: list[BulkReplaceRow] = []
    reader = csv.DictReader(io.StringIO(csv_content.strip()))
    for item in reader:
        identifier = (item.get("api_key_id") or item.get("safetyhub_key_full") or item.get("safetyhub_key_prefix") or "").strip()
        new_key = (item.get("new_upstream_key") or "").strip()
        if identifier and new_key:
            rows.append(BulkReplaceRow(identifier=identifier, new_upstream_key=new_key))
    return rows


def _build_api_key_record(
    payload: ApiKeyCreate,
    upstream_key: str,
    safetyhub_key: str,
    upstream_key_encrypted: str,
    safetyhub_key_encrypted: str,
    upstream_key_id: str | None = None,
) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=f"ak_{uuid.uuid4().hex}",
        key_hash=hash_api_key(safetyhub_key),
        key_prefix=key_prefix(safetyhub_key),
        key_suffix=key_suffix(safetyhub_key),
        name=payload.name.strip(),
        owner_user_id=payload.owner_user_id.strip(),
        owner_department=payload.owner_department,
        cost_center=payload.cost_center,
        status="active",
        provider_name=payload.provider_name.strip() or "passthrough",
        upstream_key_id=upstream_key_id,
        upstream_key_prefix=key_prefix(upstream_key),
        upstream_key_encrypted=upstream_key_encrypted,
        safetyhub_key_encrypted=safetyhub_key_encrypted,
        is_decoupled=safetyhub_key != upstream_key,
        expires_at=payload.expires_at,
        created_at=utc_now(),
    )


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def key_prefix(raw_key: str) -> str:
    return raw_key.strip()[:12]


def key_suffix(raw_key: str) -> str:
    return raw_key.strip()[-6:]


def is_record_active(record: ApiKeyRecord, now: datetime | None = None) -> bool:
    active_now = now or utc_now()
    if record.status != "active":
        return False
    if record.expires_at is not None and record.expires_at <= active_now:
        return False
    return True


def _validate_key(raw_key: str) -> None:
    if len(raw_key) < 8:
        raise ValueError("api key is too short")


def _development_data_key() -> str:
    if settings.is_production:
        raise RuntimeError(f"{settings.data_encryption_key_env} is required in production")
    seed = settings.admin_password or settings.app_name
    return f"development:{seed}"


def _fernet_key(data_key: str) -> bytes:
    digest = hashlib.sha256(data_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)

