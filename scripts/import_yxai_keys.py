import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import settings
from governance.api_keys import ApiKeyCreate, ApiKeyCrypto, hash_api_key, key_prefix, key_suffix
from storage.database import close_db, get_session_factory, init_db
from storage.models import ApiKeyRecord, utc_now

# 导入 YXAI 密钥
DEFAULT_INPUT_PATH = Path(__file__).resolve().parents[2] / "中转站" / "LLM-relay" / "yxai_token_export.json"
TARGET_PROVIDER_NAME = "oneapi_nanfu_yxai"
LEGACY_PROVIDER_NAMES = {"oneapi_yxai", TARGET_PROVIDER_NAME}


async def import_keys(input_path: Path) -> dict[str, int]:
    await init_db()
    crypto = ApiKeyCrypto()
    session_factory = get_session_factory()
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    stats = {"created": 0, "updated": 0, "skipped": 0}
    async with session_factory() as session:
        for item in items:
            normalized = normalize_item(item)
            if normalized is None:
                stats["skipped"] += 1
                continue
            existing = await find_existing(session, normalized["upstream_key_id"], normalized["upstream_key"])
            if existing is None:
                session.add(build_record(normalized, crypto))
                stats["created"] += 1
                continue
            update_record(existing, normalized, crypto)
            stats["updated"] += 1
        await session.commit()
    await close_db()
    return stats


async def find_existing(session, upstream_key_id: str, upstream_key: str) -> ApiKeyRecord | None:
    result = await session.execute(
        select(ApiKeyRecord).where(
            ApiKeyRecord.provider_name.in_(LEGACY_PROVIDER_NAMES),
            ApiKeyRecord.upstream_key_id == upstream_key_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing
    return await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.key_hash == hash_api_key(upstream_key)))


def normalize_item(item: dict) -> dict[str, str] | None:
    upstream_key = normalize_key(item.get("upstream_key") or "")
    upstream_key_id = str(item.get("upstream_key_id") or "").strip()
    name = str(item.get("name") or "").strip()
    if not upstream_key or not upstream_key_id:
        return None
    return {
        "name": name or f"yxai-token-{upstream_key_id}",
        "owner_user_id": str((item.get("raw") or {}).get("user_id") or "yxai-user"),
        "upstream_key": upstream_key,
        "upstream_key_id": upstream_key_id,
    }


def normalize_key(value: str) -> str:
    raw_key = value.strip()
    if not raw_key:
        return ""
    if raw_key.startswith("sk-"):
        return raw_key
    return f"sk-{raw_key}"


def build_record(item: dict[str, str], crypto: ApiKeyCrypto) -> ApiKeyRecord:
    upstream_key = item["upstream_key"]
    payload = ApiKeyCreate(
        name=item["name"],
        owner_user_id=item["owner_user_id"],
        upstream_key=upstream_key,
        reuse_upstream_key=True,
        provider_name=TARGET_PROVIDER_NAME,
    )
    return ApiKeyRecord(
        id=f"ak_import_{item['upstream_key_id']}",
        key_hash=hash_api_key(upstream_key),
        key_prefix=key_prefix(upstream_key),
        key_suffix=key_suffix(upstream_key),
        name=payload.name.strip(),
        owner_user_id=payload.owner_user_id.strip(),
        status="active",
        provider_name=TARGET_PROVIDER_NAME,
        upstream_key_id=item["upstream_key_id"],
        upstream_key_prefix=key_prefix(upstream_key),
        upstream_key_encrypted=crypto.encrypt(upstream_key),
        safetyhub_key_encrypted=crypto.encrypt(upstream_key),
        is_decoupled=False,
        created_at=utc_now(),
    )


def update_record(record: ApiKeyRecord, item: dict[str, str], crypto: ApiKeyCrypto) -> None:
    upstream_key = item["upstream_key"]
    record.key_hash = hash_api_key(upstream_key)
    record.key_prefix = key_prefix(upstream_key)
    record.key_suffix = key_suffix(upstream_key)
    record.name = item["name"]
    record.owner_user_id = item["owner_user_id"]
    record.status = "active"
    record.provider_name = TARGET_PROVIDER_NAME
    record.upstream_key_id = item["upstream_key_id"]
    record.upstream_key_prefix = key_prefix(upstream_key)
    record.upstream_key_encrypted = crypto.encrypt(upstream_key)
    record.safetyhub_key_encrypted = crypto.encrypt(upstream_key)
    record.is_decoupled = False
    record.revoked_at = None


def parse_args():
    parser = argparse.ArgumentParser(description="导入 yxai_token_export.json 到 SafetyHub api_keys 表")
    parser.add_argument("--input", default=str(DEFAULT_INPUT_PATH))
    return parser.parse_args()


async def main():
    args = parse_args()
    stats = await import_keys(Path(args.input))
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
