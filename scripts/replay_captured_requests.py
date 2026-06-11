from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

DEFAULT_CAPTURE_FILE = "data/capture/openai_requests.ndjson"
DEFAULT_BASE_URL = "https://yxai-api.nanfu.com"
DEFAULT_MODEL = "deepseek-v4-pro"


def iter_records(path: Path):
    if not path.exists():
        raise SystemExit(f"capture file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def build_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if path.startswith("/v1/"):
        return f"{base}{path}"
    if path.startswith("/"):
        return f"{base}/v1{path}"
    return f"{base}/v1/{path}"


async def replay_record(client: httpx.AsyncClient, record: dict[str, Any], base_url: str, api_key: str, model: str | None = None) -> None:
    path = str(record.get("path") or "")
    method = str(record.get("method") or "POST").upper()
    body = record.get("body_json")
    if not isinstance(body, dict):
        body = {}
    if model:
        body.setdefault("model", model)

    url = build_url(base_url, path)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        response = await client.request(method, url, headers=headers, json=body, timeout=60.0)
    except httpx.HTTPError as exc:
        print(f"[HTTP-ERROR] {method} {path} -> {exc.__class__.__name__}: {exc}")
        return

    snippet = response.text[:400].replace("\n", " ")
    print(f"[REPLAY] {method} {path} -> {response.status_code} len={len(response.text)} body_snip={snippet!r}")


async def replay_all(args: argparse.Namespace) -> None:
    capture_path = Path(args.capture_file).resolve()
    records = list(iter_records(capture_path))
    if args.path_filter:
        records = [r for r in records if str(r.get("path") or "").startswith(args.path_filter)]
    if args.limit and len(records) > args.limit:
        records = records[-args.limit :]

    if not records:
        print("no records to replay")
        return

    print(f"replaying {len(records)} records to {args.base_url} model={args.model or '<from record>'}")

    async with httpx.AsyncClient() as client:
        for record in records:
            await replay_record(client, record, args.base_url, args.api_key, args.model)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay captured OpenAI-compatible requests to upstream")
    parser.add_argument("--capture-file", default=DEFAULT_CAPTURE_FILE)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--path-filter", default="/v1/chat/completions")
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    import asyncio

    args = parse_args()
    asyncio.run(replay_all(args))


if __name__ == "__main__":
    main()
