from collections.abc import AsyncGenerator

import httpx


class SSEStreamProxy:
    @staticmethod
    async def proxy_stream(
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict,
    ) -> AsyncGenerator[bytes, None]:
        async with client.stream(method, url, json=body, headers=headers) as upstream:
            upstream.raise_for_status()
            async for chunk in upstream.aiter_bytes():
                if chunk:
                    yield chunk

    @staticmethod
    async def collect_stream(
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict,
    ) -> AsyncGenerator[tuple[bytes | None, str | None], None]:
        chunks: list[bytes] = []
        async with client.stream(method, url, json=body, headers=headers) as upstream:
            upstream.raise_for_status()
            async for chunk in upstream.aiter_bytes():
                if not chunk:
                    continue
                chunks.append(chunk)
                yield chunk, None
        yield None, b"".join(chunks).decode("utf-8", errors="replace")
