from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from config import Settings, settings


@dataclass(slots=True)
class KeyCreateParams:
    name: str
    owner_user_id: str
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class UpstreamKeyInfo:
    key_id: str
    key_prefix: str
    key_suffix: str
    key_secret: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class KeyProviderError(RuntimeError):
    pass


class KeyProvider(ABC):
    @abstractmethod
    async def create_key(self, params: KeyCreateParams) -> UpstreamKeyInfo:
        raise NotImplementedError

    @abstractmethod
    async def revoke_key(self, key_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_key_info(self, key_id: str) -> UpstreamKeyInfo | None:
        raise NotImplementedError

    @abstractmethod
    async def list_keys(self) -> list[UpstreamKeyInfo]:
        raise NotImplementedError

    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def upstream_base_url(self) -> str:
        raise NotImplementedError


def create_key_provider(active_settings: Settings | None = None) -> KeyProvider:
    active_settings = active_settings or settings
    provider_type = active_settings.key_provider_type.strip().lower()
    if provider_type in {"passthrough", ""}:
        from governance.providers.passthrough import PassthroughKeyProvider

        return PassthroughKeyProvider()
    if provider_type == "static":
        from governance.providers.static_key import StaticKeyProvider

        return StaticKeyProvider(active_settings)
    if provider_type == "oneapi_nanfu_yxai":
        from governance.providers.oneapi_nanfu_yxai import OneApiNanfuYxaiKeyProvider

        return OneApiNanfuYxaiKeyProvider(active_settings)
    raise KeyProviderError(f"unsupported key provider type: {provider_type}")
