from governance.key_provider import KeyCreateParams, KeyProvider, KeyProviderError, UpstreamKeyInfo


class PassthroughKeyProvider(KeyProvider):
    @property
    def provider_name(self) -> str:
        return "passthrough"

    @property
    def upstream_base_url(self) -> str:
        return ""

    async def create_key(self, params: KeyCreateParams) -> UpstreamKeyInfo:
        raise KeyProviderError("passthrough provider does not support key creation")

    async def revoke_key(self, key_id: str) -> bool:
        raise KeyProviderError("passthrough provider does not support key revoke")

    async def get_key_info(self, key_id: str) -> UpstreamKeyInfo | None:
        return None

    async def list_keys(self) -> list[UpstreamKeyInfo]:
        return []
