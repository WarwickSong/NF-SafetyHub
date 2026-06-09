from __future__ import annotations

import asyncio
from typing import Any

import httpx

from config import Settings
from governance.key_provider import KeyCreateParams, KeyProvider, KeyProviderError, UpstreamKeyInfo
from governance.api_keys import key_prefix, key_suffix


class OneApiNanfuYxaiKeyProvider(KeyProvider):
    def __init__(self, settings: Settings):
        self._settings = settings
        self._base_url = settings.key_provider_base_url.rstrip("/")
        self._username = settings.key_provider_username
        self._password = settings.get_secret(settings.key_provider_password_env)
        self._auth_version = settings.key_provider_auth_version
        self._timeout = settings.key_provider_timeout_seconds
        self._login_retries = settings.key_provider_login_retries
        self._login_retry_delay = settings.key_provider_login_retry_delay_seconds
        self._request_retries = settings.key_provider_request_retries
        self._request_retry_delay = settings.key_provider_request_retry_delay_seconds
        self._default_remain_quota = settings.key_provider_default_remain_quota
        self._default_unlimited_quota = settings.key_provider_default_unlimited_quota

    @property
    def provider_name(self) -> str:
        return "oneapi_nanfu_yxai"

    @property
    def upstream_base_url(self) -> str:
        return self._base_url

    async def create_key(self, params: KeyCreateParams) -> UpstreamKeyInfo:
        self._validate_config()
        session_cookie, user_id = await self._login()
        token = await self._request(
            "POST",
            "/api/token/",
            session_cookie,
            user_id,
            json={
                "name": params.name,
                "remain_quota": int(params.metadata.get("remain_quota", self._default_remain_quota)),
                "unlimited_quota": bool(params.metadata.get("unlimited_quota", self._default_unlimited_quota)),
            },
        )
        token_data = token.get("data") or {}
        token_id = token_data.get("id")
        if token_id is None:
            token_id = await self._find_latest_token_id(session_cookie, user_id, params.name)
        key_secret = await self._get_full_key(session_cookie, user_id, str(token_id))
        return UpstreamKeyInfo(
            key_id=str(token_id),
            key_prefix=key_prefix(key_secret),
            key_suffix=key_suffix(key_secret),
            key_secret=key_secret,
            metadata={"raw_create_response": token_data},
        )

    async def revoke_key(self, key_id: str) -> bool:
        self._validate_config()
        if not key_id:
            raise KeyProviderError("upstream key id is required")
        session_cookie, user_id = await self._login()
        await self._request("DELETE", f"/api/token/{key_id}", session_cookie, user_id)
        return True

    async def get_key_info(self, key_id: str) -> UpstreamKeyInfo | None:
        keys = await self.list_keys()
        for item in keys:
            if item.key_id == key_id:
                return item
        return None

    async def list_keys(self) -> list[UpstreamKeyInfo]:
        self._validate_config()
        session_cookie, user_id = await self._login()
        items = []
        page = 1
        page_size = 100
        while True:
            payload = await self._request("GET", "/api/token/", session_cookie, user_id, params={"p": page, "size": page_size})
            data = payload.get("data") or {}
            page_items = data.get("items") or []
            for item in page_items:
                token_id = item.get("id")
                if token_id is None:
                    continue
                items.append(
                    UpstreamKeyInfo(
                        key_id=str(token_id),
                        key_prefix="",
                        key_suffix="",
                        key_secret=None,
                        metadata={"raw": item},
                    )
                )
            total = data.get("total") or data.get("total_count") or data.get("count")
            if len(page_items) < page_size:
                break
            if total is not None and page * page_size >= int(total):
                break
            page += 1
        return items

    async def _find_latest_token_id(self, session_cookie: str, user_id: str, name: str) -> str:
        payload = await self._request("GET", "/api/token/", session_cookie, user_id, params={"p": 1, "size": 100})
        items = (payload.get("data") or {}).get("items") or []
        matches = [item for item in items if item.get("name") == name and item.get("id") is not None]
        if not matches:
            raise KeyProviderError("created upstream token id not found")
        latest = max(matches, key=lambda item: int(item.get("id") or 0))
        return str(latest["id"])

    async def _get_full_key(self, session_cookie: str, user_id: str, token_id: str) -> str:
        payload = await self._request("POST", f"/api/token/{token_id}/key", session_cookie, user_id, origin=True)
        key_value = ((payload.get("data") or {}).get("key") or "").strip()
        if not key_value:
            raise KeyProviderError("upstream key secret is empty")
        if key_value.startswith("sk-"):
            return key_value
        return f"sk-{key_value}"

    async def _login(self) -> tuple[str, str]:
        last_error = None
        for attempt in range(1, self._login_retries + 1):
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/api/user/login",
                    json={"username": self._username, "password": self._password},
                    headers=self._login_headers(),
                )
            if response.status_code == 429:
                last_error = KeyProviderError("upstream login rate limited")
                await asyncio.sleep(self._login_retry_delay * attempt)
                continue
            try:
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                raise KeyProviderError(f"upstream login failed: {exc}") from exc
            session_cookie = response.cookies.get("session")
            user_id = str((payload.get("data") or {}).get("id") or "")
            if not session_cookie or not user_id:
                raise KeyProviderError("upstream login did not return session or user id")
            return session_cookie, user_id
        raise last_error or KeyProviderError("upstream login failed")

    async def _request(
        self,
        method: str,
        path: str,
        session_cookie: str,
        user_id: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        origin: bool = False,
    ) -> dict[str, Any]:
        last_error = None
        for attempt in range(1, self._request_retries + 1):
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method,
                    f"{self._base_url}{path}",
                    json=json,
                    params=params,
                    cookies={"session": session_cookie},
                    headers=self._auth_headers(user_id, origin),
                )
            if response.status_code == 429:
                last_error = KeyProviderError("upstream request rate limited")
                await asyncio.sleep(self._request_retry_delay * attempt)
                continue
            try:
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                raise KeyProviderError(f"upstream request failed: {exc}") from exc
            if not payload.get("success", True):
                raise KeyProviderError(f"upstream request returned failure: {payload}")
            return payload
        raise last_error or KeyProviderError("upstream request failed")

    def _validate_config(self) -> None:
        missing = []
        if not self._base_url:
            missing.append("KEY_PROVIDER_BASE_URL")
        if not self._username:
            missing.append("KEY_PROVIDER_USERNAME")
        if not self._password:
            missing.append(self._settings.key_provider_password_env)
        if not self._auth_version:
            missing.append("KEY_PROVIDER_AUTH_VERSION")
        if missing:
            raise KeyProviderError(f"missing key provider settings: {', '.join(missing)}")

    def _login_headers(self) -> dict[str, str]:
        return {
            "Referer": f"{self._base_url}/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

    def _auth_headers(self, user_id: str, origin: bool = False) -> dict[str, str]:
        headers = {
            "Referer": f"{self._base_url}/console/token",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "auth-version": self._auth_version,
            "new-api-user": str(user_id),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        if origin:
            headers["origin"] = self._base_url
        return headers
