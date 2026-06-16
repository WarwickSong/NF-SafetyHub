import argparse
import asyncio
import base64
import hashlib
import hmac
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_project_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_project_env()

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import settings
from governance.api_keys import ApiKeyCrypto
from storage.models import ApiKeyRecord


class LegacyApiKeyCrypto:
    def __init__(self, data_key: str):
        self._data_key = data_key

    def decrypt(self, value: str) -> str:
        try:
            version, salt_value, nonce_value, ciphertext_value, tag_value = value.split(":", 4)
            if version != "v1":
                raise ValueError("unsupported envelope")
            salt = _unb64(salt_value)
            nonce = _unb64(nonce_value)
            ciphertext = _unb64(ciphertext_value)
            expected_tag = _unb64(tag_value)
        except Exception as exc:
            raise ValueError("invalid encrypted value") from exc
        enc_key, mac_key = self._derive_keys(salt)
        header = b"v1" + salt + nonce + ciphertext
        actual_tag = hmac.new(mac_key, header, hashlib.sha256).digest()
        if not hmac.compare_digest(actual_tag, expected_tag):
            raise ValueError("encrypted value integrity check failed")
        plaintext = _xor_bytes(ciphertext, _keystream(enc_key, nonce, len(ciphertext)))
        return plaintext.decode("utf-8")

    def _derive_keys(self, salt: bytes) -> tuple[bytes, bytes]:
        root = hashlib.pbkdf2_hmac("sha256", self._data_key.encode("utf-8"), salt, 200_000, dklen=64)
        return root[:32], root[32:]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate api_keys encrypted fields from legacy v1 to Fernet v2")
    parser.add_argument("--db-url", default=os.getenv("POSTGRES_DB_URL") or settings.db_url)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    data_key = os.getenv(settings.data_encryption_key_env) or settings.get_secret(settings.data_encryption_key_env)
    if not data_key:
        raise SystemExit(f"{settings.data_encryption_key_env} is required to decrypt existing APIKey records")
    engine = create_async_engine(args.db_url, future=True, connect_args=_connect_args(args.db_url))
    legacy_crypto = LegacyApiKeyCrypto(data_key)
    fernet_crypto = ApiKeyCrypto(data_key)
    try:
        stats = await migrate(engine, legacy_crypto, fernet_crypto, args.dry_run)
    finally:
        await engine.dispose()
    print(f"scanned={stats['scanned']} migrated={stats['migrated']} already_v2={stats['already_v2']} empty={stats['empty']}")


async def migrate(engine, legacy_crypto: LegacyApiKeyCrypto, fernet_crypto: ApiKeyCrypto, dry_run: bool) -> dict[str, int]:
    stats = {"scanned": 0, "migrated": 0, "already_v2": 0, "empty": 0}
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(select(ApiKeyRecord))
        records = list(result.scalars().all())
        for record in records:
            stats["scanned"] += 1
            changed = False
            for field_name in ("upstream_key_encrypted", "safetyhub_key_encrypted"):
                value = getattr(record, field_name) or ""
                if not value:
                    stats["empty"] += 1
                    continue
                if value.startswith("v2:"):
                    stats["already_v2"] += 1
                    continue
                plaintext = legacy_crypto.decrypt(value)
                setattr(record, field_name, fernet_crypto.encrypt(plaintext))
                changed = True
            if changed:
                stats["migrated"] += 1
        if dry_run:
            await session.rollback()
        else:
            await session.commit()
    return stats


def _connect_args(db_url: str) -> dict[str, int]:
    if db_url.startswith("sqlite+aiosqlite:///"):
        return {"timeout": 30}
    return {}


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(output[:length])


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right, strict=False))


if __name__ == "__main__":
    asyncio.run(main())
