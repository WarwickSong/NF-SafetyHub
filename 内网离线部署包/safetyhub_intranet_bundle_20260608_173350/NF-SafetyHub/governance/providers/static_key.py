from config import Settings
from governance.key_provider import KeyCreateParams, KeyProvider, KeyProviderError, UpstreamKeyInfo


class StaticKeyProvider(KeyProvider):
    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def provider_name(self) -> str:
        return "static"

    @property
    def upstream_base_url(self) -> str:
        return self._settings.upstream_url

    async def create_key(self, params: KeyCreateParams) -> UpstreamKeyInfo:
        raise KeyProviderError("static provider does not support key creation")

    async def revoke_key(self, key_id: str) -> bool:
        raise KeyProviderError("static provider does not support key revoke")

    async def get_key_info(self, key_id: str) -> UpstreamKeyInfo | None:
        return None

    async def list_keys(self) -> list[UpstreamKeyInfo]:
        return []
