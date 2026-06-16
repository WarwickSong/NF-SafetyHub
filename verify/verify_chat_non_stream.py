import argparse
import json
import os
import re
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx
import yaml

DEFAULT_BASE_URL = os.getenv("SAFETYHUB_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_API_KEY = os.getenv("SAFETYHUB_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
DEFAULT_MODEL = os.getenv("SAFETYHUB_MODEL", "deepseek-v4-pro")
DEFAULT_RULES_PATH = Path(os.getenv("SAFETYHUB_RULES_PATH", Path(__file__).resolve().parents[1] / "engine" / "rules_config.yaml"))


def endpoint_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/v1/chat/completions"


def build_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def build_payload(model: str, prompt: str, stream: bool) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个简洁的测试助手。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "stream": stream,
    }


# ---------------------------------------------------------------------------
# 规则展示与本地预检
# ---------------------------------------------------------------------------

def load_rules_config(rules_path: Path) -> dict[str, Any]:
    if not rules_path.exists():
        return {}
    with rules_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def enabled_block_keyword_rules(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        rule
        for rule in config.get("keyword_rules", []) or []
        if rule.get("enabled", True) and rule.get("level", "block") == "block"
    ]


def enabled_block_regex_rules(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        rule
        for rule in config.get("regex_rules", []) or []
        if rule.get("enabled", True) and rule.get("level", "block") == "block"
    ]


def print_block_rules(rules_path: Path) -> None:
    config = load_rules_config(rules_path)
    keyword_rules = enabled_block_keyword_rules(config)
    regex_rules = enabled_block_regex_rules(config)
    print(f"规则文件: {rules_path}")
    print("\n以下内容命中后会被 SafetyHub 拦截，并返回伪装回复：")
    print("\n关键词 block 规则：")
    if not keyword_rules:
        print("- 未找到启用中的关键词 block 规则")
    for rule in keyword_rules:
        keywords = "、".join(str(keyword) for keyword in rule.get("keywords", []))
        print(f"- {rule.get('id', '')} {rule.get('name', '')}: {keywords}")
    print("\n正则 block 规则：")
    if not regex_rules:
        print("- 未找到启用中的正则 block 规则")
    for rule in regex_rules:
        print(f"- {rule.get('id', '')} {rule.get('name', '')}: {rule.get('description') or rule.get('pattern', '')}")
    print("\n提示：warn 规则只记录提醒，不会触发当前的拦截伪装回复。")


def build_local_matcher(rules_path: Path):
    config = load_rules_config(rules_path)
    keyword_rules = enabled_block_keyword_rules(config)
    regex_rules = enabled_block_regex_rules(config)
    compiled_regex_rules = []
    for rule in regex_rules:
        flags = re.IGNORECASE if rule.get("ignore_case", False) else 0
        try:
            compiled_regex_rules.append((re.compile(rule["pattern"], flags), rule))
        except (KeyError, re.error):
            continue

    def match_prompt(prompt: str) -> None:
        hits: list[str] = []
        for rule in keyword_rules:
            case_sensitive = rule.get("case_sensitive", False)
            match_mode = rule.get("match_mode", "contains")
            search_text = prompt if case_sensitive else prompt.lower()
            for keyword in rule.get("keywords", []):
                search_keyword = str(keyword) if case_sensitive else str(keyword).lower()
                if keyword_matches(search_text, search_keyword, match_mode):
                    hits.append(f"{rule.get('id', '')} {rule.get('name', '')} / {keyword}")
                    break
        for pattern, rule in compiled_regex_rules:
            if pattern.search(prompt):
                hits.append(f"{rule.get('id', '')} {rule.get('name', '')}")
        if hits:
            print("本地预检：预计会被拦截：")
            for hit in hits:
                print(f"- {hit}")
        else:
            print("本地预检：未命中 block 规则，预计会透传到上游。")

    return match_prompt


def keyword_matches(text: str, keyword: str, match_mode: str) -> bool:
    if not keyword:
        return False
    if match_mode == "exact":
        return text == keyword
    if match_mode == "prefix":
        return text.startswith(keyword)
    return keyword in text


# ---------------------------------------------------------------------------
# 非流式发送 — 一次性返回完整 JSON
# ---------------------------------------------------------------------------

def send_non_stream(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    model: str,
    prompt: str,
) -> bool:
    start_time = time.perf_counter()
    response = client.post(url, headers=headers, json=build_payload(model, prompt, False))
    elapsed = time.perf_counter() - start_time
    print(f"HTTP {response.status_code}，耗时 {elapsed:.2f}s")

    content_type = response.headers.get("content-type", "<无 content-type>")
    request_id = response.headers.get("x-request-id", "<无 x-request-id>")
    if response.status_code >= 400:
        print_limited_text(response.text)
        return False

    try:
        payload = response.json()
    except json.JSONDecodeError:
        print_limited_text(response.text)
        return False

    print(f"响应 ID: {payload.get('id', '<无 id>')}")
    print(f"响应对象: {payload.get('object', '<无 object>')}")
    print(f"Content-Type: {content_type}")
    print(f"X-Request-ID: {request_id}")

    content = extract_non_stream_content(payload)
    print(f"助手回复: {content or '<未解析到 choices[0].message.content>'}")
    return bool(content or payload)


def extract_non_stream_content(payload: dict[str, Any]) -> str:
    try:
        return payload["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        return ""


# ---------------------------------------------------------------------------
# 交互循环
# ---------------------------------------------------------------------------

def print_startup(args: argparse.Namespace) -> None:
    print(f"目标接口: {endpoint_url(args.base_url)}")
    print(f"模型: {args.model}")
    print(f"API Key: {'已设置' if args.api_key else '未设置'}")
    print("输入 exit、quit 或 q 可退出。")


def ask_prompt() -> str | None:
    try:
        prompt = input("\n请输入要发送给模型的内容> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if prompt.lower() in {"exit", "quit", "q"}:
        return None
    return prompt


def print_limited_text(text: str, limit: int = 2000) -> None:
    if len(text) <= limit:
        print(text)
        return
    print(text[:limit])
    print(f"... 已截断，原始长度 {len(text)} 字符")


def build_client(timeout_seconds: float) -> httpx.Client:
    timeout = httpx.Timeout(connect=10.0, read=timeout_seconds, write=10.0, pool=10.0)
    return httpx.Client(timeout=timeout)


def run_interactive_loop(args: argparse.Namespace, before_send=None) -> int:
    print_startup(args)
    with build_client(args.timeout) as client:
        while True:
            prompt = ask_prompt()
            if prompt is None:
                print("已退出。")
                return 0
            if not prompt:
                print("输入为空，已跳过。")
                continue
            if before_send:
                before_send(prompt)
            try:
                url = endpoint_url(args.base_url)
                headers = build_headers(args.api_key)
                send_non_stream(client, url, headers, args.model, prompt)
            except httpx.HTTPError as exc:
                print(f"请求失败: {exc}")
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="整体传输模式：演示 SafetyHub 在非流式下的拦截与正常透传")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="SafetyHub 服务地址，默认读取 SAFETYHUB_BASE_URL 或 http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="上游 API Key，默认读取 SAFETYHUB_API_KEY 或 OPENAI_API_KEY")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="模型名，默认读取 SAFETYHUB_MODEL 或 deepseek-v4-pro")
    parser.add_argument("--timeout", type=float, default=120.0, help="请求超时时间，单位秒")
    parser.add_argument("--rules-path", type=Path, default=DEFAULT_RULES_PATH, help="规则文件路径")
    parser.add_argument("--no-local-check", action="store_true", help="发送前不做本地命中预检")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)

    print("=" * 60)
    print("  SafetyHub 整体传输验证")
    print("  模式: 非流式 — 一次性返回完整 JSON")
    print("=" * 60)
    print_block_rules(args.rules_path)
    print()

    before_send = None if args.no_local_check else build_local_matcher(args.rules_path)
    return run_interactive_loop(args, before_send=before_send)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
