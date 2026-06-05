# LLM-SafetyHub 代码结构框架规划

> 本文档定义项目的代码结构、模块职责、接口规范和数据流，为团队开发提供明确的代码级指引。

---

## 一、项目目录结构

当前代码结构如下；阶段 1~6 核心能力已落地，KeyProvider 抽象、Provider 实现、APIKey 管理、文生图图片资产归档和后台页面已进入当前结构。当前开发范围收敛到阶段 6A 单实例 Docker 生产稳定性与高并发治理；阶段 7 及之后暂不开发，告警、图片资产治理增强、文件安全运行模块仅保留规划，不作为当前上线阻塞项。

```text
NF-SafetyHub/
├── main.py
├── config.py
├── dependencies.py
├── proxy/
│   ├── relay.py
│   ├── fake_response.py
│   ├── header_policy.py
│   ├── upstream_router.py
│   └── stream.py
├── engine/
│   ├── base.py
│   ├── models.py
│   ├── normalizer.py
│   ├── rules_config.yaml
│   ├── rules_keyword.py
│   ├── rules_regex.py
│   └── scanner.py
├── governance/
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── oneapi_nanfu_yxai.py
│   │   ├── passthrough.py
│   │   └── static_key.py
│   ├── __init__.py
│   ├── api_keys.py
│   └── key_provider.py
├── file_security/
│   └── __init__.py
├── observability/
│   ├── health.py
│   └── request_id.py
├── storage/
│   ├── migrations/
│   │   └── .gitkeep
│   ├── admin_ops.py
│   ├── archive.py
│   ├── audit.py
│   ├── database.py
│   └── models.py
├── admin/
│   ├── router.py
│   ├── schemas.py
│   └── static/
│       ├── api_keys.html
│       ├── approvals.html
│       ├── archives.html
│       ├── blocks.html
│       ├── index.html
│       ├── login.html
│       ├── observations.html
│       ├── rules.html
│       ├── settings.html
│       ├── css/style.css
│       └── js/app.js
├── middleware/
│   ├── auth.py
│   ├── concurrency_limit.py      # 阶段 6A：/v1/* 全局有界并发队列
│   └── identity.py
├── notify/
│   └── __init__.py
├── nginx/
│   └── nginx.conf
├── scripts/
│   ├── import_yxai_keys.py
│   └── init_db.py
├── tests/
│   ├── test_admin_auth.py
│   ├── test_admin_stage4.py
│   ├── test_api_keys.py
│   ├── test_archive.py
│   ├── test_audit.py
│   ├── test_fake_response.py
│   ├── test_header_policy.py
│   ├── test_health.py
│   ├── test_keyword.py
│   ├── test_models.py
│   ├── test_observations.py
│   ├── test_regex.py
│   ├── test_relay.py
│   ├── test_rules_config.py
│   ├── test_rules_reload.py
│   ├── test_scanner.py
│   └── test_upstream_router.py
├── verify/
│   ├── verify_chat_non_stream.py
│   └── verify_chat_stream.py
├── 交付运行手册/
├── 产品研发控制/
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── requirements.txt
├── pytest.ini
├── .env.example
├── .gitignore
└── README.md
```

---

## 二、核心模块详细设计

### 2.1 `main.py` — 应用入口

```python
import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from admin.router import router as admin_router
from config import settings, validate_startup_settings
from engine.rules_keyword import KeywordScanner
from engine.rules_regex import RegexScanner
from engine.scanner import ScannerOrchestrator
from governance.api_keys import ApiKeyService
from governance.key_provider import create_key_provider
from middleware.auth import AdminStaticAuthMiddleware
from middleware.identity import ApiKeyIdentityMiddleware
from observability.health import router as health_router
from observability.request_id import RequestIdMiddleware
from proxy.relay import router as relay_router
from proxy.upstream_router import get_default_upstream_router
from storage.database import close_db, get_session_factory, init_db

ADMIN_STATIC_DIR = "admin/static"


async def periodic_rules_reload(scanner: ScannerOrchestrator, interval_seconds: int) -> None:
    interval = max(1, interval_seconds)
    while True:
        await asyncio.sleep(interval)
        with suppress(Exception):
            await scanner.reload_all()


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_settings(settings)
    await init_db()
    scanner = ScannerOrchestrator()
    scanner.register(KeywordScanner(settings.rules_config_path))
    scanner.register(RegexScanner(settings.rules_config_path))
    reload_task = asyncio.create_task(periodic_rules_reload(scanner, settings.rules_reload_interval))
    app.state.scanner = scanner
    app.state.session_factory = get_session_factory()
    app.state.key_provider = create_key_provider(settings)
    app.state.api_key_service = ApiKeyService(app.state.session_factory, key_provider=app.state.key_provider)
    app.state.upstream_router = get_default_upstream_router()
    app.state.rules_reload_task = reload_task
    try:
        yield
    finally:
        reload_task.cancel()
        with suppress(asyncio.CancelledError):
            await reload_task
        await close_db()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(V1ConcurrencyLimitMiddleware)
app.add_middleware(ApiKeyIdentityMiddleware)
app.add_middleware(AdminStaticAuthMiddleware)
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(admin_router, prefix="/admin/api", tags=["admin"])
app.include_router(relay_router, prefix="/v1", tags=["relay"])
app.mount("/admin", StaticFiles(directory=ADMIN_STATIC_DIR, html=True), name="admin")
```

**职责**

- FastAPI 应用创建和生命周期管理
- 启动配置校验、数据库初始化和连接释放
- Scanner 初始化、定时规则热加载和注入
- KeyProvider、ApiKeyService、上游路由初始化和注入
- Request ID、`/v1/*` 并发闸门、APIKey 身份、后台静态页认证中间件注册
- 应用生命周期内初始化并释放共享上游 HTTP client、归档/审计后台队列和统计缓存
- 健康检查、管理 API、中继路由和后台静态页面挂载

---

### 2.2 `config.py` — 配置管理

```python
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "LLM-SafetyHub"
    environment: str = "development"
    debug: bool = True

    upstream_url: str = ""                     # 默认中转站地址
    upstream_timeout_connect: int = 10         # 连接超时(秒)
    upstream_timeout_read: int = 120           # 读取超时(秒)
    upstream_timeout_pool: int = 5             # 上游连接池等待超时(秒)
    upstream_max_connections: int = 200        # 阶段 6A：每 worker 上游最大连接数
    upstream_max_keepalive_connections: int = 100
    upstream_keepalive_expiry: int = 30

    v1_max_inflight: int = 250                 # 阶段 6A：每 worker /v1/* 最大在途请求数；4 worker 总目标 1000
    v1_max_queue_size: int = 500               # 阶段 6A：每 worker /v1/* 最大排队数；4 worker 总目标 2000
    v1_queue_timeout_seconds: float = 15       # 阶段 6A：排队等待超时，可通过 .env 调整
    admin_stats_cache_seconds: int = 10        # 阶段 6A：后台统计短缓存
    archive_queue_max_size: int = 5000         # 阶段 6A：归档后台队列上限
    archive_batch_size: int = 50
    archive_flush_interval_seconds: float = 1
    archive_max_payload_bytes: int = 262144

    rules_config_path: Path = Path("engine/rules_config.yaml")
    rules_reload_interval: int = 5             # 规则热加载间隔(秒)
    scanner_order: list[str] = Field(default_factory=lambda: ["keyword", "regex"])

    db_url: str = "sqlite+aiosqlite:///./data/safetyhub.db"
    archive_retention_days: int = 180
    audit_retention_days: int = 365
    data_encryption_enabled: bool = False
    data_encryption_key_env: str = "SAFETYHUB_DATA_KEY"

    key_provider_type: str = "passthrough"
    key_provider_admin_token: str = ""
    key_provider_base_url: str = ""
    key_provider_username: str = ""
    key_provider_password_env: str = "KEY_PROVIDER_PASSWORD"
    key_provider_auth_version: str = ""
    key_provider_default_remain_quota: int = 1000000
    key_provider_default_unlimited_quota: bool = True
    key_provider_timeout_seconds: int = 30
    key_provider_login_retries: int = 3
    key_provider_login_retry_delay_seconds: float = 10
    key_provider_request_retries: int = 3
    key_provider_request_retry_delay_seconds: float = 2

    admin_username: str = "admin"
    admin_password: str = ""                   # 环境变量注入
    admin_ip_whitelist: list[str] = Field(default_factory=list)

    webhook_url: str = ""                      # 阶段 8 告警启用时使用
    webhook_type: str = "wecom"                # wecom / feishu
    approval_webhook_url: str = ""
    approval_timeout_minutes: int = 30
    alert_silence_rule_minutes: int = 5
    alert_silence_user_minutes: int = 2
    alert_hourly_limit: int = 50

    request_max_body_mb: int = 20
    file_scan_enabled: bool = False
    file_max_size_mb: int = 50
    file_allowed_types: list[str] = ["txt", "md", "pdf", "docx", "xlsx", "csv"]

    uvicorn_workers: int = 4
    uvicorn_host: str = "0.0.0.0"
    uvicorn_port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
```

**设计要点**

- 使用 `pydantic-settings` 统一管理环境变量和 .env 文件
- 敏感配置（密码、Webhook URL、加密密钥、上游 Key）通过环境变量注入，不硬编码
- 启动时进行配置校验，生产环境缺少 `admin_password`、`upstream_url` 或弱密码时直接启动失败
- 规则文件路径可配置，方便测试时使用不同的规则集
- APIKey 与上游 Key 映射配置已在阶段 5/6 启用；模型权限、token 额度、速率限制和资源能力权限由中转站作为权威系统管理，SafetyHub 不做本地资源授权判定
- 阶段 6A 新增的并发、队列、上游连接池、管理端缓存和归档削峰配置均按每 worker 生效；单实例 Docker 内启用多个 worker 时，需要按容器总目标折算每 worker 配置
- KeyProvider 配置支持 `passthrough` / `static` / `oneapi_nanfu_yxai`，通用 `openai_compat` 和自动续约迁移留待后续增强
- 数据保留、文件扫描、临时审批和告警默认可关闭，避免 MVP 阶段扩大实现范围

---

### 2.3 `proxy/relay.py` — 核心中继转发

```python
from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
from engine.scanner import ScannerOrchestrator
from proxy.fake_response import generate_fake_response
from proxy.stream import SSEStreamProxy
from storage.archive import ArchiveWriter
from storage.audit import AuditWriter
router = APIRouter()


@router.post("/chat/completions")
async def chat_completions(request: Request):
    return await relay_openai_compatible(request, "chat/completions")


@router.api_route("/{upstream_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def relay_openai_compatible(request: Request, upstream_path: str):
    path = f"/v1/{upstream_path.strip('/')}"
    body, raw_body = await read_request_body(request, path)
    if path == "/v1/chat/completions":
        scan_text = extract_text_from_request(path, body)
        if scan_text:
            scan_result = await request.app.state.scanner.scan(scan_text)
            if scan_result.blocked:
                return await generate_fake_response(body, scan_result, body.get("stream", False))

    return await relay_to_upstream(request, path, body, raw_body)


def extract_text_from_request(path: str, body: dict) -> str:
    ...


def extract_text_from_messages(messages: list) -> str:
    ...
```

**核心流程**

```
请求到达 /v1/{path}
  │
  ├─ 阶段 6A：进入 /v1/* 全局有界并发队列
  │     ├─ in_flight 未满 → 获取令牌并进入业务链路
  │     ├─ in_flight 已满但 queue 未满 → 等待令牌
  │     ├─ queue 满 → 返回 429/503
  │     ├─ 等待超时 → 返回 429/503
  │     └─ 流式与非流式统一使用该队列，不单独拆分流式并发池
  │
  ├─ 判断接口类型
  │     ├─ Chat → 提取 messages 文本并进入 Scanner
  │     └─ 非 Chat（Embeddings/Completions/Responses/Images/未知接口/GET/DELETE/非 JSON/multipart）→ 阶段 1 默认透明透传
  │
  ├─ Chat Scanner 扫描
  │     │
  │     ├─ blocked → 返回 Chat Completions 兼容伪装回复
  │     └─ passed/warn → 转发到中转站
  │                   │
  │                   └─ Chat 流式：SSE 逐 chunk 透传
  │
  ├─ 非 Chat 请求
  │     └─ 默认透传到中转站；后续仅按明确业务需要增加脱敏或资产归档
  │
  └─ 阶段 6A：审计/归档进入有界后台队列，队列满时按降级策略保存摘要或跳过完整内容
```

---

### 2.4 `proxy/stream.py` — SSE 流式处理

```python
import httpx


class SSEStreamProxy:
    CHUNK_SIZE = 4096

    @staticmethod
    async def proxy_stream(
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: dict,
        body: dict,
    ) -> AsyncGenerator[bytes, None]:
        async with client.stream(
            method, url, json=body, headers=headers
        ) as upstream:
            async for chunk in upstream.aiter_bytes():
                yield chunk

    @staticmethod
    async def collect_stream(
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: dict,
        body: dict,
    ) -> AsyncGenerator[tuple[bytes, str], None]:
        full_content = []
        async with client.stream(
            method, url, json=body, headers=headers
        ) as upstream:
            async for chunk in upstream.aiter_bytes():
                yield chunk, None
                full_content.append(chunk)
        yield None, b"".join(full_content).decode("utf-8")
```

**设计要点**

- `proxy_stream`：纯透传模式，chunk 到达即转发，延迟最低
- `collect_stream`：透传 + 收集模式，在透传的同时拼接完整响应，用于消息归档
- 阶段 6A 默认使用应用生命周期内共享的 `httpx.AsyncClient`，不在每个请求中重复创建 client
- 阶段 6A 流式归档必须受 `stream_archive_max_bytes` / `archive_max_payload_bytes` 约束，超过上限保存截断标记和原始字节数
- 两种模式通过配置切换，默认使用 `collect_stream`（需要归档完整响应）

---

### 2.5 `proxy/fake_response.py` — 伪装回复

```python
from engine.models import ScannerResult
import uuid
import time
import json


TEMPLATES = {
    "block": "抱歉，我无法处理您的请求。您输入的内容可能包含敏感信息，请检查后重试。如需帮助，请联系信息安全团队。",
    "warn": "请注意，您输入的内容可能包含敏感信息，已记录并通知安全团队。",
}


async def generate_fake_response(
    request_body: dict,
    scan_result: ScannerResult,
    is_stream: bool,
) -> JSONResponse | StreamingResponse:
    template = TEMPLATES.get(scan_result.level, TEMPLATES["block"])
    model = request_body.get("model", "gpt-3.5-turbo")

    if is_stream:
        return StreamingResponse(
            _stream_fake_chunks(template, model),
            media_type="text/event-stream",
        )
    else:
        return JSONResponse(_build_non_stream_response(template, model))


def _build_non_stream_response(content: str, model: str) -> dict:
    return {
        "id": f"chatcmpl-safetyhub-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def _stream_fake_chunks(content: str, model: str):
    ...
```

---

### 2.6 `engine/` — 安全扫描引擎

#### 2.6.1 `engine/models.py` — 数据模型

```python
from dataclasses import dataclass


@dataclass
class ScannerResult:
    hit: bool
    rule_id: str = ""
    rule_name: str = ""
    level: str = "pass"
    matched_text: str = ""
    position: tuple[int, int] = (0, 0)
    scanner_type: str = ""

    @property
    def blocked(self) -> bool:
        return self.hit and self.level == "block"

    @property
    def warned(self) -> bool:
        return self.hit and self.level == "warn"


@dataclass
class AggregatedScanResult:
    results: list[ScannerResult]

    @property
    def blocked(self) -> bool:
        return any(r.blocked for r in self.results)

    @property
    def warned(self) -> bool:
        return any(r.warned for r in self.results)

    @property
    def block_result(self) -> ScannerResult | None:
        return next((r for r in self.results if r.blocked), None)

    @property
    def warn_results(self) -> list[ScannerResult]:
        return [r for r in self.results if r.warned]
```

#### 2.6.2 `engine/base.py` — Scanner 抽象基类

```python
from abc import ABC, abstractmethod
from engine.models import ScannerResult


class BaseScanner(ABC):
    @abstractmethod
    async def scan(self, text: str) -> list[ScannerResult]:
        ...

    @abstractmethod
    async def reload(self) -> None:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
```

#### 2.6.3 `engine/scanner.py` — 调度引擎

```python
from engine.base import BaseScanner
from engine.models import AggregatedScanResult, ScannerResult


class ScannerOrchestrator:
    def __init__(self):
        self._scanners: list[BaseScanner] = []

    def register(self, scanner: BaseScanner) -> None:
        self._scanners.append(scanner)

    async def scan(self, text: str) -> AggregatedScanResult:
        all_results: list[ScannerResult] = []
        for scanner in self._scanners:
            try:
                results = await scanner.scan(text)
                all_results.extend(results)
                if any(r.blocked for r in results):
                    return AggregatedScanResult(results=all_results)
            except Exception:
                continue
        return AggregatedScanResult(results=all_results)

    async def reload_all(self) -> None:
        for scanner in self._scanners:
            await scanner.reload()
```

#### 2.6.4 `engine/rules_keyword.py` — 关键词 Scanner

```python
from engine.base import BaseScanner
from engine.models import ScannerResult
from config import Settings
import yaml
from pathlib import Path


class KeywordScanner(BaseScanner):
    def __init__(self, config_path: Path):
        self._config_path = config_path
        self._rules: list[dict] = []
        self._load_rules()

    def _load_rules(self) -> None:
        with open(self._config_path) as f:
            data = yaml.safe_load(f)
        self._rules = data.get("keyword_rules", [])

    async def scan(self, text: str) -> list[ScannerResult]:
        results = []
        for rule in self._rules:
            for keyword in rule["keywords"]:
                search_text = text if rule.get("case_sensitive", False) else text.lower()
                search_keyword = keyword if rule.get("case_sensitive", False) else keyword.lower()
                idx = search_text.find(search_keyword)
                if idx != -1:
                    results.append(ScannerResult(
                        hit=True,
                        rule_id=rule["id"],
                        rule_name=rule["name"],
                        level=rule["level"],
                        matched_text=self._mask_text(keyword),
                        position=(idx, idx + len(keyword)),
                        scanner_type="keyword",
                    ))
                    if rule.get("match_mode", "contains") == "contains":
                        break
        return results

    async def reload(self) -> None:
        self._load_rules()

    @property
    def name(self) -> str:
        return "keyword"

    @staticmethod
    def _mask_text(text: str) -> str:
        if len(text) <= 2:
            return text[0] + "*"
        return text[0] + "*" * (len(text) - 2) + text[-1]
```

#### 2.6.5 `engine/rules_regex.py` — 正则 Scanner

```python
from engine.base import BaseScanner
from engine.models import ScannerResult
import yaml
import re
from pathlib import Path


class RegexScanner(BaseScanner):
    MATCH_TIMEOUT_MS = 100

    def __init__(self, config_path: Path):
        self._config_path = config_path
        self._rules: list[dict] = []
        self._compiled: list[tuple[re.Pattern, dict]] = []
        self._load_rules()

    def _load_rules(self) -> None:
        with open(self._config_path) as f:
            data = yaml.safe_load(f)
        self._rules = data.get("regex_rules", [])
        self._compiled = [
            (re.compile(r["pattern"]), r) for r in self._rules
        ]

    async def scan(self, text: str) -> list[ScannerResult]:
        results = []
        for pattern, rule in self._compiled:
            try:
                match = pattern.search(text)
                if match:
                    results.append(ScannerResult(
                        hit=True,
                        rule_id=rule["id"],
                        rule_name=rule["name"],
                        level=rule["level"],
                        matched_text=self._mask_text(match.group()),
                        position=match.span(),
                        scanner_type="regex",
                    ))
            except (re.error, TimeoutError):
                continue
        return results

    async def reload(self) -> None:
        self._load_rules()

    @property
    def name(self) -> str:
        return "regex"

    @staticmethod
    def _mask_text(text: str) -> str:
        if len(text) <= 4:
            return text[:2] + "**"
        return text[:2] + "*" * (len(text) - 4) + text[-2:]
```

---

### 2.7 `storage/` — 存储层

#### 2.7.1 `storage/database.py` — 数据库管理

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import settings

engine = create_async_engine(settings.db_url, echo=settings.debug)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    from storage.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    await engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
```

#### 2.7.2 `storage/models.py` — ORM 模型

```python
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class MessageArchive(Base):
    __tablename__ = "message_archives"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    api_key_id = Column(String(64), nullable=True, index=True)
    model = Column(String(64), nullable=False, index=True)
    capability = Column(String(32), default="chat", index=True)
    # ---- 阶段 3 双份 prompt 存储（F6.1-C5）：原始 + 脱敏后 ----
    prompt_original = Column(Text, nullable=False)
    prompt_desensitized = Column(Text, nullable=True)
    is_desensitized = Column(Boolean, default=False, index=True)
    response = Column(Text, nullable=True)
    is_stream = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    blocked_rule_id = Column(String(64), nullable=True)
    approval_id = Column(String(64), nullable=True, index=True)
    file_ids = Column(Text, nullable=True)
    image_metadata = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    completed_at = Column(DateTime, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    # ---- v1.2 Key 级安全策略关联（v1.0 仅建字段，不写入） ----
    security_policy_id = Column(String(64), nullable=True, index=True)

    __table_args__ = (
        Index("ix_archives_user_time", "user_id", "created_at"),
        Index("ix_archives_api_key_model_time", "api_key_id", "model", "created_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    api_key_id = Column(String(64), nullable=True, index=True)
    model = Column(String(64), nullable=True, index=True)
    capability = Column(String(32), nullable=True)
    rule_id = Column(String(64), nullable=False, index=True)
    rule_name = Column(String(128), nullable=False)
    rule_level = Column(String(16), nullable=False)
    scanner_type = Column(String(32), nullable=False)
    matched_snippet = Column(Text, nullable=False)
    full_text_hash = Column(String(64), nullable=False)
    action_taken = Column(String(16), nullable=False)
    approval_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    # ---- v1.2 Key 级安全策略关联（v1.0 仅建字段，不写入） ----
    security_policy_id = Column(String(64), nullable=True, index=True)

    __table_args__ = (
        Index("ix_audits_rule_time", "rule_id", "created_at"),
        Index("ix_audits_user_time", "user_id", "created_at"),
    )


class ApiKeyRecord(Base):
    __tablename__ = "api_keys"

    id = Column(String(64), primary_key=True)
    key_hash = Column(String(128), unique=True, nullable=False)
    key_prefix = Column(String(16), nullable=False)
    key_suffix = Column(String(8), nullable=False)
    name = Column(String(128), nullable=True)
    owner_user_id = Column(String(128), nullable=False, index=True)
    owner_department = Column(String(128), nullable=True, index=True)
    cost_center = Column(String(64), nullable=True, index=True)
    status = Column(String(16), default="active", index=True)
    # ---- v1.1 中转站映射字段（v1.0 仅建表，不写入） ----
    provider_name = Column(String(64), nullable=False, default="passthrough")
    upstream_route_id = Column(String(64), nullable=True)
    upstream_key_id = Column(String(128), nullable=True)
    upstream_key_prefix = Column(String(16), nullable=True)
    upstream_key_encrypted = Column(Text, nullable=True)
    safetyhub_key_encrypted = Column(Text, nullable=True)
    # ---- 阶段 5 K-Sync / K-Decoupled 模式标记（F15.1.5） ----
    # False: K-Sync（safetyhub_key 与 upstream_key 一致，默认）
    # True:  K-Decoupled（中转站 Key 已被替换或独立生成，与前哨站 Key 解耦）
    is_decoupled = Column(Boolean, default=False, index=True)
    # ---- v1.2 F18/F19 Key 级安全策略与审批链关联（v1.0 仅建字段，NULL 表示走全局） ----
    security_policy_id = Column(String(64), nullable=True, index=True)
    approval_chain_id = Column(String(64), nullable=True, index=True)
    # ---- 生命周期 ----
    created_at = Column(DateTime, server_default=func.now(), index=True)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(String(64), primary_key=True)
    request_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    api_key_id = Column(String(64), nullable=True, index=True)
    model = Column(String(64), nullable=False)
    capability = Column(String(32), nullable=False)
    rule_id = Column(String(64), nullable=False, index=True)
    status = Column(String(16), default="pending", index=True)
    approver = Column(String(128), nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    # ---- v1.2 F19 审批链关联（v1.0 仅建字段，NULL 表示无审批链） ----
    chain_id = Column(String(64), nullable=True, index=True)
    current_level = Column(Integer, default=0)
    escalated_at = Column(DateTime, nullable=True)


class SecurityPolicy(Base):
    """v1.2 F18 Key 级安全策略表。
    v1.0 仅建表，不写入。"""
    __tablename__ = "security_policies"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    # 相对于全局规则的覆盖（JSON）：{"KW-001": "disabled", "RG-003": "warn"}
    rule_overrides = Column(Text, nullable=False, default="{}")
    # 决策阈值
    block_threshold = Column(String(16), default="block")
    warn_to_block_keywords = Column(Text, nullable=True)
    # 不可降级的高危规则白名单（JSON 数组）
    immutable_rules = Column(Text, nullable=True)
    # 策略继承（最多 3 级）
    inherit_from = Column(String(64), nullable=True, index=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ApprovalChain(Base):
    """v1.2 F19 审批链表。
    v1.0 仅建表，不写入。"""
    __tablename__ = "approval_chains"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    # 多级审批节点（JSON 数组）：
    # [{"level": 1, "approver_type": "user", "approver_id": "xxx",
    #   "timeout_minutes": 30, "on_timeout": "escalate"}, ...]
    chain_definition = Column(Text, nullable=False, default="[]")
    # 触发条件
    trigger_rule_levels = Column(Text, nullable=True)
    trigger_capabilities = Column(Text, nullable=True)
    # 整链超时策略：auto_reject / auto_approve / hold
    escalation_policy = Column(String(32), default="auto_reject")
    # 不可审批的高危规则（这些规则即使绑定审批链也直接 block）
    blocked_rules = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ImageAsset(Base):
    __tablename__ = "image_assets"

    id = Column(String(64), primary_key=True)
    request_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    model = Column(String(64), nullable=True, index=True)
    prompt_hash = Column(String(64), nullable=True)
    asset_index = Column(Integer, default=0)
    source_type = Column(String(32), nullable=False)
    source_url = Column(Text, nullable=True)
    local_path = Column(Text, nullable=True)
    sha256 = Column(String(64), nullable=True, index=True)
    mime_type = Column(String(64), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    download_status = Column(String(32), default="pending", index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class FileScanRecord(Base):
    __tablename__ = "file_scan_records"

    id = Column(String(64), primary_key=True)
    request_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    file_name = Column(String(256), nullable=False)
    file_type = Column(String(32), nullable=False, index=True)
    file_size = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)
    extracted_text_hash = Column(String(64), nullable=True)
    scan_status = Column(String(32), nullable=False, index=True)
    action_taken = Column(String(32), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class AdminOperationLog(Base):
    __tablename__ = "admin_operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_user = Column(String(128), nullable=False, index=True)
    operation = Column(String(64), nullable=False, index=True)
    target_type = Column(String(64), nullable=False)
    target_id = Column(String(128), nullable=True)
    request_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
```

#### 2.7.3 `storage/archive.py` — 消息归档

```python
from storage.database import async_session
from storage.models import MessageArchive
from sqlalchemy import select, func, desc


class ArchiveWriter:
    @staticmethod
    async def write(archive: MessageArchive) -> None:
        async with async_session() as session:
            session.add(archive)
            await session.commit()

    @staticmethod
    async def update_response(request_id: str, response: str, completed_at, latency_ms: int) -> None:
        async with async_session() as session:
            stmt = select(MessageArchive).where(MessageArchive.request_id == request_id)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record:
                record.response = response
                record.completed_at = completed_at
                record.latency_ms = latency_ms
                await session.commit()


class ArchiveReader:
    @staticmethod
    async def list_records(
        user_id: str | None = None,
        start_time=None,
        end_time=None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[MessageArchive], int]:
        ...

    @staticmethod
    async def get_by_id(record_id: int) -> MessageArchive | None:
        ...

    @staticmethod
    async def get_stats() -> dict:
        ...
```

#### 2.7.4 `storage/audit.py` — 审计日志

```python
from storage.database import async_session
from storage.models import AuditLog
from sqlalchemy import select


class AuditWriter:
    @staticmethod
    async def write(audit: AuditLog) -> None:
        async with async_session() as session:
            session.add(audit)
            await session.commit()


class AuditReader:
    @staticmethod
    async def list_records(
        user_id: str | None = None,
        rule_id: str | None = None,
        rule_level: str | None = None,
        start_time=None,
        end_time=None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AuditLog], int]:
        ...

    @staticmethod
    async def get_by_id(record_id: int) -> AuditLog | None:
        ...

```

当前 `AuditReader` 提供分页查询、详情和计数能力；审计 CSV/JSON 导出统一放入阶段 8 增强，不作为阶段 4~6 当前 API。

---

### 2.8 `admin/` — 管理后台

管理员前端属于本项目交付物，放在 `admin/static/` 目录中，由 FastAPI 挂载静态文件；后端提供 `/admin/api/*` 管理接口。当前前端包含仪表盘、拦截记录、消息归档、上线观测、规则管理、系统设置、APIKey 管理和审批占位。APIKey 页面已在阶段 5/6 升级为可操作页面；模型/token/资源权限由中转站管理，SafetyHub 后台仅展示边界提示或 Provider 引用。

#### 2.8.1 `admin/router.py` — API 路由

```python
from fastapi import APIRouter, Depends, Query, Request, Response, status
from admin.schemas import *
from governance.api_keys import ApiKeyCreate, ApiKeyService
from storage.archive import ArchiveReader
from storage.audit import AuditReader
from storage.admin_ops import AdminOperationReader, AdminOperationWriter

router = APIRouter(dependencies=[Depends(require_admin_access)])


@router.post("/login", response_model=AdminLoginResponse)
async def login(payload: AdminLoginRequest, response: Response):
    ...


@router.get("/observations/recent", response_model=ObservationListResponse)
async def recent_observations(request: Request, limit: int = Query(default=10, ge=1, le=50)):
    ...


@router.get("/archives", response_model=ArchiveListResponse)
async def list_archives(request: Request, limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    ...


@router.get("/archives/{archive_id}", response_model=ArchiveDetail)
async def get_archive(request: Request, archive_id: int):
    ...


@router.get("/audits", response_model=AuditListResponse)
async def list_audits(request: Request, limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    ...


@router.get("/audits/{audit_id}", response_model=AuditDetail)
async def get_audit(request: Request, audit_id: int):
    ...


@router.get("/admin-ops", response_model=AdminOperationListResponse)
async def list_admin_operations(request: Request, limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    ...


@router.get("/stats", response_model=AdminStatsResponse)
async def admin_stats(request: Request):
    ...


@router.get("/rules", response_model=RuleListResponse)
async def list_rules(request: Request):
    ...


@router.post("/rules/reload", response_model=RulesReloadResponse)
async def reload_rules(request: Request):
    ...


@router.get("/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys(request: Request, limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    ...


@router.post("/api-keys", response_model=ApiKeyMutationResponse)
async def create_api_key(request: Request, payload: ApiKeyCreateRequest):
    ...


@router.post("/api-keys/{api_key_id}/reveal", response_model=ApiKeyRevealResponse)
async def reveal_api_key(request: Request, response: Response, api_key_id: str):
    ...


@router.post("/api-keys/{api_key_id}/revoke", response_model=ApiKeyMutationResponse)
async def revoke_api_key(request: Request, api_key_id: str):
    ...


@router.post("/api-keys/{api_key_id}/replace-upstream-key", response_model=ApiKeyMutationResponse)
async def replace_upstream_key(request: Request, api_key_id: str, payload: ApiKeyReplaceRequest):
    ...


@router.post("/api-keys/bulk-replace-upstream-keys", response_model=ApiKeyBulkReplaceResponse)
async def bulk_replace_upstream_keys(request: Request, payload: ApiKeyBulkReplaceRequest):
    ...
```

#### 2.8.2 `admin/schemas.py` — Pydantic 模型

```python
from pydantic import BaseModel
from datetime import datetime


class ArchiveItem(BaseModel):
    id: int
    request_id: str
    user_id: str
    model: str
    is_stream: bool
    is_blocked: bool
    blocked_rule_id: str | None
    prompt_tokens: int
    completion_tokens: int
    created_at: datetime
    latency_ms: int | None

    class Config:
        from_attributes = True


class ArchiveDetailResponse(ArchiveItem):
    prompt: str
    response: str


class ArchiveListResponse(BaseModel):
    items: list[ArchiveItem]
    total: int
    page: int
    page_size: int


class AuditItem(BaseModel):
    id: int
    request_id: str
    user_id: str
    rule_id: str
    rule_name: str
    rule_level: str
    scanner_type: str
    matched_snippet: str
    action_taken: str
    created_at: datetime

    class Config:
        from_attributes = True


class AuditListResponse(BaseModel):
    items: list[AuditItem]
    total: int
    page: int
    page_size: int


class StatsResponse(BaseModel):
    total_requests: int
    total_blocks: int
    total_warnings: int
    active_users: int
    top_rules: list[dict]
    daily_trend: list[dict]
```

---

### 2.9 `notify/` — 告警通知

当前 `notify/` 仅保留包初始化文件，告警通知尚未进入主链路。阶段 8 暂不开发，生产上线前不新增 `notify/webhook.py`、`notify/rate_limiter.py` 和对应测试，也不在 `proxy/relay.py` 中集成企微/飞书 Webhook 推送与频率控制。

阶段 8 长期规划目标模块：

| 模块 | 职责 |
|------|------|
| `notify/webhook.py` | 构造企微/飞书告警消息，发送 block/warn 高风险事件 |
| `notify/rate_limiter.py` | 按规则、用户和小时维度做告警频控 |
| `tests/test_webhook.py` | 验证告警 payload、频控和发送失败降级 |

---

### 2.10 `middleware/` — 中间件

#### 2.10.1 `middleware/auth.py`

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import secrets
from config import settings


class AdminAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/admin"):
            return await call_next(request)
        if settings.admin_ip_whitelist:
            client_ip = request.client.host
            if client_ip not in settings.admin_ip_whitelist:
                return Response(status_code=403)
        auth = request.headers.get("Authorization")
        if not auth or not self._check_basic_auth(auth):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": "Basic"},
            )
        return await call_next(request)

    @staticmethod
    def _check_basic_auth(auth_header: str) -> bool:
        import base64
        try:
            scheme, credentials = auth_header.split()
            if scheme.lower() != "basic":
                return False
            decoded = base64.b64decode(credentials).decode("utf-8")
            username, password = decoded.split(":", 1)
            return (
                secrets.compare_digest(username, settings.admin_username)
                and secrets.compare_digest(password, settings.admin_password)
            )
        except Exception:
            return False
```

#### 2.10.2 `middleware/identity.py`

| 能力 | 当前行为 |
|------|----------|
| Authorization 解析 | 解析 `/v1/*` 请求的 Bearer Key，计算哈希后匹配 `api_keys` |
| 过渡透传 | `api_keys` 表为空时保持阶段 1~4 透传行为 |
| 有效性校验 | 创建第一条 APIKey 后校验 active/revoked/expired 状态 |
| 上游 Key 映射 | 读取并解密 `upstream_key_encrypted`，写入请求上下文供 Header Policy 替换上游 Authorization |
| 权限边界 | 不做模型/token/资源权限 allowlist，相关 401/403/429 由中转站判定并透传 |

#### 2.10.3 `middleware/concurrency_limit.py` — 阶段 6A `/v1/*` 并发闸门

| 能力 | 设计要求 |
|------|----------|
| 作用范围 | 仅作用于 `/v1/*`，不包裹 `/admin/*`、`/admin/api/*`、`/health/*` 和静态资源 |
| 最大在途 | 使用 `v1_max_inflight` 控制每 worker 同时进入业务链路的请求数，默认 4 worker 下每 worker 250、容器总目标 1000 |
| 有界排队 | 使用 `v1_max_queue_size` 控制等待令牌的请求数，默认 4 worker 下每 worker 500、容器总目标 2000，队列满时立即返回 429 或 503 |
| 排队超时 | 使用 `v1_queue_timeout_seconds` 控制等待令牌最长时间，超时后返回明确错误，不允许无限挂起 |
| 流式口径 | 流式与非流式统一进入 `/v1/*` 并发闸门，不单独维护流式并发池 |
| 可观测字段 | 在响应头或日志中保留 request_id、queue_wait_ms、inflight、queue_size、reject_reason 等摘要字段 |
| 多 worker 口径 | 进程内计数不跨 worker；单实例 Docker 内多 worker 时必须按容器总目标折算每 worker 配置，并可通过 `.env` 或等价部署配置调整 |
| 安全边界 | 不做按 Key 限流，不做上游熔断，不改变 APIKey 身份校验和中转站权限判定职责 |

---

### 2.11 `runtime/` — 阶段 6A 运行期资源

阶段 6A 可新增轻量运行期模块，用于承载单实例生产高并发治理，避免把队列、连接池和缓存逻辑散落在 `relay.py`、`admin/router.py` 和 `storage/*` 中。

| 模块 | 职责 | 当前阶段口径 |
|------|------|--------------|
| `runtime/upstream_client.py` | 创建和关闭共享 `httpx.AsyncClient`，封装连接池、keepalive、pool timeout 配置 | P0，实现后由 `proxy/relay.py` 复用 |
| `runtime/archive_queue.py` | 维护归档/审计有界队列、批量消费、flush 和 shutdown drain | P1，先覆盖 Chat 归档和审计 |
| `runtime/admin_cache.py` | 提供短 TTL 内存缓存，用于 `/admin/api/stats` 等高压查询保护 | P0，单 worker 内缓存即可 |
| `runtime/metrics_snapshot.py` | 保存轻量运行快照，如 inflight、queue_size、reject_count、archive_queue_size | P1，先供日志和后台状态展示使用 |

---

### 2.12 `governance/` — 身份、权限与审批预留

| 模块 | 职责 | v1.0 行为 | 后续启用方向 |
|------|------|-----------|--------------|
| `identity.py` | 解析用户、APIKey、来源 IP、客户端标识 | 统一生成 `RequestContext`，写入日志/归档/审计 | 接入企业 SSO、JWT claims、APIKey 归属映射 |
| `api_keys.py` | APIKey 元数据、状态、所属用户/部门、上游 Key 映射 | 存储哈希、前后缀、加密 upstream_key、加密 safetyhub_key，不做资源授权 | 已支持 APIKey 启停、吊销、过期、上游 Key 替换、Provider 创建和 reveal |
| `key_provider.py` | KeyProvider 抽象基类与工厂 | 已定义接口，按 `key_provider_type` 实例化 Provider | 新增 Provider 不改 relay/scanner/archive/audit 核心链路 |
| `providers/passthrough.py` | 默认占位实现 | 所有写操作抛 `KeyProviderError` 或返回空 | 始终保留作为 fallback |
| `providers/static_key.py` | 静态 Key 提供者 | 查询占位，不创建/吊销 | 从配置读取中转站 Key，绑定时手动选择 |
| `providers/oneapi_nanfu_yxai.py` | 南孚 yxai OneAPI/OneHub 适配器 | 已实现登录、创建、取完整 Key、分页列表和吊销 | 调用 `/api/token`、`/api/token/{id}/key`、`DELETE /api/token/{id}` |
| `providers/openai_compat.py` | OpenAI 兼容协议适配器 | 待实现 | 调用 `/v1/api-keys` 接口 |
| `quota.py` | F20 中转站配额与速率观测 | 不实现 | 如 Provider 支持，阶段 10 只读查询或跳转中转站，不提供本地配额/速率拦截 |
| `security_policy.py` | F18 Key 级安全策略 | 不实现 | 阶段 9 启用，提供 load/inheritance/apply_overrides |
| `approval_chain.py` | F19 审批链路由 | 不实现 | 阶段 9 启用，提供 resolve_approver / on_approval_decision / on_timeout |
| `approval_scheduler.py` | F19 审批超时扫描器 | 不实现 | 阶段 9 启用，定时扫描超时审批请求 |
| `upstream_permission_view.py` | 中转站资源权限只读引用 | 不实现 | 如中转站开放接口，仅展示或跳转中转站侧模型/token/能力权限配置 |
| `approval.py` | 临时审批流程 | 预留数据模型和接口，不阻塞主链路 | 支持敏感请求人工审批后一次性放行 |

**预留原则**

- APIKey 永不明文入库，只存哈希、前后缀展示、创建时间、状态、归属信息、加密后的 upstream_key 和加密后的 safetyhub_key
- 模型权限、token 额度、速率限制和资源能力权限由中转站作为权威系统管理，SafetyHub 不预留本地权限字段
- SafetyHub 可在 `RequestContext`、归档和审计中记录 `api_key_id`、`model`、`capability`，用于安全治理、追溯和告警，不用于资源授权判定
- 阶段 1~4 不实现复杂权限决策，阶段 5 只启用 APIKey 有效性校验和上游 Key 映射

#### 2.11.1 `governance/key_provider.py` — KeyProvider 抽象层

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class UpstreamKeyInfo:
    key_id: str                       # 中转站侧的 Key ID
    key_prefix: str                   # 前后缀拼接，例如 "sk-ab...wxyz"
    key_secret: str | None            # 完整上游 Key（Provider create 时返回；SafetyHub 加密后写入 upstream_key_encrypted / safetyhub_key_encrypted）
    metadata: dict


@dataclass
class KeyCreateParams:
    name: str
    owner_user_id: str
    expires_at: str | None = None
    metadata: dict | None = None


class KeyProvider(ABC):
    """中转站 API Key 管理的抽象接口。

    不同中转站的 Key 创建/吊销/查询方式不同，
    通过实现这个接口来适配。
    切换中转站 = 替换 Provider 实现 + 修改配置，
    SafetyHub 核心链路与前端零改动。
    """

    @abstractmethod
    async def create_key(self, params: KeyCreateParams) -> UpstreamKeyInfo: ...

    @abstractmethod
    async def revoke_key(self, key_id: str) -> bool: ...

    @abstractmethod
    async def get_key_info(self, key_id: str) -> UpstreamKeyInfo | None: ...

    @abstractmethod
    async def list_keys(self) -> list[UpstreamKeyInfo]: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def upstream_base_url(self) -> str: ...


def create_key_provider(provider_type: str, **kwargs) -> KeyProvider:
    """KeyProvider 工厂方法，根据 settings.key_provider_type 实例化。"""
    if provider_type == "passthrough":
        from governance.providers.passthrough import PassthroughKeyProvider
        return PassthroughKeyProvider(**kwargs)
    if provider_type == "static":
        from governance.providers.static_key import StaticKeyProvider
        return StaticKeyProvider(**kwargs)
    if provider_type == "oneapi_nanfu_yxai":
        from governance.providers.oneapi_nanfu_yxai import OneApiNanfuYxaiKeyProvider
        return OneApiNanfuYxaiKeyProvider(**kwargs)
    if provider_type == "openai_compat":
        from governance.providers.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(**kwargs)
    raise ValueError(f"Unknown key provider: {provider_type}")
```

#### 2.11.2 阶段 3 预留改动清单

> 这三个改动在阶段 1~3 透传模式下**对运行行为零影响**，但是阶段 5 启用 APIKey 管理时**避免改动核心链路代码**的关键。

| 改动 ID | 文件 | 改动内容 | 兼容性保证 |
|--------|------|---------|-----------|
| **R1** | `proxy/header_policy.py` | `build_upstream_headers(headers, request_id, upstream_api_key=None)` 新增可选参数；当 `upstream_api_key is None` 时保持原有透传行为，否则剥离原始 Authorization 并替换为 `Bearer {upstream_api_key}` | 所有现有调用点传 `None`，行为不变；新增单元测试覆盖两条分支 |
| **R2** | `storage/models.py` | 新增 `ApiKeyRecord` ORM 模型（包含阶段 5/6 全部字段），通过 `Base.metadata.create_all` 在启动时一并创建 `api_keys` 表 | 表存在但无人写入，不影响任何路径；不需要迁移脚本 |
| **R3** | `config.py` | 新增 `key_provider_type: str = "passthrough"` 和 `key_provider_admin_token: str = ""` 配置项 | 默认值表示透传模式；阶段 1~5 不实例化 Provider，配置仅用于占位 |

**改动量评估**：3 个文件，每个不超过 30 行；新增 1 个单元测试文件，约 50 行。

#### 2.11.3 阶段 5/6 启用流程

```
1. ✅ 实现 governance/key_provider.py 抽象基类
2. ✅ 实现 governance/providers/{passthrough, static_key, oneapi_nanfu_yxai}.py；openai_compat 待后续增强
3. ✅ 在 main.py lifespan 中调用 create_key_provider，注入到 app.state.key_provider
4. ✅ 实现 middleware/identity.py：
   ├─ 解析客户端 Authorization → 计算 key_hash
   ├─ 查询 api_keys 表 → 取出 upstream_key_encrypted → 解密
   └─ 写入 request.state.upstream_api_key
5. ✅ 修改 proxy/relay.py：调用 build_upstream_headers 时传入 request.state.upstream_api_key
6. ✅ 新增 admin/router.py 中的 /admin/api/api-keys CRUD、reveal、吊销、单条/批量替换接口
7. ✅ 新增 admin/static/api_keys.html 的编辑能力
```

> **关键**：以上 7 步全部是新增或封装，**不修改 R1、R2、R3 引入的接口签名和数据 schema**，因此核心链路（scanner/relay/archive/audit）和前端通用页面无需任何改动。

#### 2.11.4 v1.0 扩展预留改动清单（F18/F19/F20）

> 这一批预留对应《功能定义规划》F18 Key 级安全策略、F19 审批链路由、F20 细粒度配额。
> 与 R1/R2/R3 同样满足"v1.0 仅 schema，运行行为零变化"原则。

| 改动 ID | 文件 | 改动内容 | 关联功能 | 兼容性保证 |
|--------|------|---------|---------|-----------|
| **R6** | `storage/models.py` | 明确 `ApiKeyRecord` 不新增 F20 模型配额、能力配额、速率限制和用量快照字段 | F20 | 资源权限与配额由中转站作为权威系统管理，SafetyHub schema 不污染 |
| **R7** | `storage/models.py` | `ApiKeyRecord` 新增 2 个 F18/F19 字段：`security_policy_id`、`approval_chain_id`；`MessageArchive`、`AuditLog` 新增 `security_policy_id` 字段；`ApprovalRequest` 新增 `chain_id`、`current_level`、`escalated_at` 字段；`ApiKeyRecord` 新增 `cost_center` 字段 | F18 / F19 | 全部 NULL 默认，老数据无需回填 |
| **R8** | `storage/models.py` | 新增 `SecurityPolicy` 与 `ApprovalChain` 两张 ORM 表，随 `create_all` 自动建表 | F18 / F19 | 表存在但无人写入，零影响 |

**改动量评估**：1 个文件 `storage/models.py`，总计约 60 行新增代码；新增 1 个单元测试，约 40 行。

#### 2.11.5 v1.2 启用 SecurityPolicy 流程

```
1. 实现 governance/security_policy.py：
   ├─ load_policy(policy_id) → SecurityPolicy
   ├─ resolve_inheritance(policy) → 合并继承链（最多 3 级）
   └─ apply_overrides(rules, policy) → 返回应用 diff 后的有效规则集
2. 修改 engine/scanner.py：
   ├─ scan(text, policy=None) → 默认 None 走全局规则（向下兼容）
   └─ 缓存策略编译结果，避免重复计算
3. 修改 proxy/relay.py：
   ├─ 从 request.state.api_key_record 读取 security_policy_id
   ├─ 加载策略并传给 scanner.scan(text, policy)
   └─ 命中后写入 audit_log.security_policy_id 和 message_archive.security_policy_id
4. 实现 admin/api/security-policies CRUD 接口
5. 实现 admin/static/security_policies.html 编辑页面
```

> **关键**：scanner.scan 接口签名通过默认参数 `policy=None` 向下兼容，所有现有调用点不需要改动。

#### 2.11.6 阶段 9 启用 ApprovalChain 流程

```
1. 实现 governance/approval_chain.py：
   ├─ resolve_approver(api_key, rule) → 根据 chain_definition 计算当前审批人
   ├─ on_approval_decision(request_id, decision) → 推进到下一级或结束
   └─ on_timeout(request_id) → 按 on_timeout 策略升级或拒绝
2. 实现 governance/approval_scheduler.py：定时扫描超时审批请求
3. 修改 notify/approval_webhook.py：审批通知按解析出的当前审批人发送
4. 实现 admin/api/approval-chains CRUD 接口
5. 实现 admin/static/approval_chains.html 编辑页面
```

> **关键**：审批链是阶段 9 新增的能力，所以"审批链"和"审批"是同时新增的，不存在改造已稳定代码的问题。

#### 2.11.7 阶段 10 启用 F20 中转站配额与速率观测流程

```
1. 扩展 KeyProvider 可选查询能力：
   ├─ get_key_quota_status(api_key_id) → 中转站配额/速率状态
   └─ get_key_permission_url(api_key_id) → 中转站控制台跳转链接
2. 修改 admin/api/api-keys：
   ├─ Provider 支持时返回只读 quota_status 或 permission_url
   └─ Provider 不支持时显示“由中转站管理”
3. 增强 admin/static/api_keys.html：只读展示资源权限状态或跳转中转站控制台
```

> **关键**：模型权限、token 额度、速率限制和资源能力权限由中转站作为权威系统管理，SafetyHub 不实现本地配额检查，也不在 `api_keys` 表保存配额字段。

### 2.12 `file_security/` — 文件上传安全预留

| 模块 | 职责 |
|------|------|
| `extractor.py` | 从 TXT/Markdown/CSV/PDF/DOCX/XLSX 中抽取文本，失败时返回不可解析状态 |
| `sanitizer.py` | 对可重写文本进行脱敏，保留原始文件哈希和脱敏文件哈希 |
| `router.py` | 预留文件解析和检测接口，后续兼容 OpenAI Files/Responses/Assistants 等文件入口 |

**处理策略**

- 能解析的文件先抽取文本，再进入同一套 `ScannerOrchestrator`
- 命中 `block` 时默认拒绝上传；命中 `warn` 时可进入人工审批或仅告警放行
- 对 PDF 图片、扫描件、压缩包、二进制文件等不可解析内容，默认按高风险策略处理：拒绝、人工审批或只允许白名单用户上传
- v1.0 先预留接口与数据模型，不默认启用文件内容改写；真正脱敏重写放到 v1.2+，避免破坏文件格式

### 2.13 `observability/` — 可观测性与运行基线

| 能力 | 要求 |
|------|------|
| Request ID | 统一读取或生成 `X-Request-ID`，贯穿日志、归档、审计、告警、上游请求 |
| 健康检查 | `/health/live` 只判断进程存活，`/health/ready` 检查数据库、规则、上游配置 |
| 指标 | 暴露请求数、拦截数、扫描耗时、上游耗时、归档失败、告警失败、SSE 连接数 |
| 结构化日志 | JSON 日志字段包含 request_id、user_id、api_key_id、model、status、latency、rule_id |
| 数据治理 | 定期执行归档清理、数据库备份、恢复验证，默认不在日志中记录 prompt/response 原文 |

---

## 三、数据流图

### 3.1 正常请求（未命中规则）

```
客户端                    SafetyHub                         中转站
  │                         │                                │
  │── POST /v1/chat/... ──→│                                │
  │                         │── 1. 提取 messages 文本         │
  │                         │── 2. Scanner 扫描 → pass        │
  │                         │── 3. 异步写入 Archive(pending)  │
  │                         │── 4. 转发请求 ────────────────→│
  │                         │                                │── 调用模型
  │                         │←── 5. 透传响应 ←──────────────│
  │←── 透传响应 ───────────│                                │
  │                         │── 6. 异步更新 Archive(response) │
```

### 3.2 命中拦截规则

```
客户端                    SafetyHub                         中转站
  │                         │                                │
  │── POST /v1/chat/... ──→│                                │
  │                         │── 1. 提取 messages 文本         │
  │                         │── 2. Scanner 扫描 → BLOCK       │
  │                         │── 3. 生成伪装回复               │
  │                         │── 4. 异步写入 Archive(blocked)  │
  │                         │── 5. 异步写入 AuditLog          │
  │                         │── 6. 异步推送 Webhook 告警      │
  │←── 伪装回复 ───────────│                                │
  │                         │       (请求未到达中转站)         │
```

### 3.3 流式请求

```
客户端                    SafetyHub                         中转站
  │                         │                                │
  │── POST (stream:true) ─→│                                │
  │                         │── 1. 扫描 → pass               │
  │                         │── 2. 转发请求 ────────────────→│
  │                         │                                │── 开始生成
  │                         │←── chunk 1 ←─────────────────│
  │←── chunk 1 ────────────│                                │
  │                         │←── chunk 2 ←─────────────────│
  │←── chunk 2 ────────────│                                │
  │                         │←── [DONE] ←──────────────────│
  │←── [DONE] ─────────────│                                │
  │                         │── 3. 拼接完整响应               │
  │                         │── 4. 异步更新 Archive           │
```

---

## 四、依赖清单

### 4.1 `requirements.txt`

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
httpx>=0.27.0
pydantic>=2.6.0
pydantic-settings>=2.2.0
sqlalchemy[asyncio]>=2.0.0
aiosqlite>=0.20.0
pyyaml>=6.0
watchfiles>=0.21.0
python-multipart>=0.0.9
```

### 4.2 开发依赖

```
pytest>=8.0.0
pytest-asyncio>=0.23.0
httpx  # 测试中使用 httpx.AsyncClient 作为 TestClient
ruff>=0.3.0
mypy>=1.8.0
```

---

## 五、Docker 部署配置

### 5.1 `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/nginx/ssl

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### 5.2 `docker-compose.yml`

```yaml
version: "3.8"

services:
  safetyhub:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - ${SAFETYHUB_DATA_DIR:-./data}:/app/data
      - ${SAFETYHUB_RULES_CONFIG:-./engine/rules_config.yaml}:/app/engine/rules_config.yaml
    ports:
      - "127.0.0.1:8000:8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health/ready')"]
      interval: 30s
      timeout: 5s
      retries: 3

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - ./admin/static:/usr/share/nginx/html/admin:ro
    depends_on:
      - safetyhub
```

---

## 六、编码规范

### 6.1 通用规范

| 规范项 | 要求 |
|--------|------|
| Python 版本 | 3.12+ |
| 类型标注 | 所有函数参数和返回值必须标注类型 |
| 异步优先 | 所有 I/O 操作使用 async/await |
| 异常处理 | 禁止裸 `except:`，必须指定异常类型 |
| 日志 | 使用 `logging` 模块，禁止 `print()` |
| 敏感信息 | 日志和错误信息中禁止打印 prompt 原文 |

### 6.2 安全编码规范

| 规范项 | 要求 |
|--------|------|
| SQL 注入 | 使用 SQLAlchemy ORM，禁止拼接 SQL |
| 密码比较 | 使用 `secrets.compare_digest`，禁止 `==` |
| 正则安全 | 设置匹配超时，防止 ReDoS |
| 路径遍历 | 规则文件路径不接收用户输入 |
| 命令注入 | 不调用 `subprocess` / `os.system` |

### 6.3 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 文件名 | snake_case | `rules_keyword.py` |
| 类名 | PascalCase | `KeywordScanner` |
| 函数名 | snake_case | `extract_text_from_messages` |
| 常量 | UPPER_SNAKE_CASE | `MATCH_TIMEOUT_MS` |
| 配置项 | snake_case | `upstream_url` |
| 环境变量 | UPPER_SNAKE_CASE | `UPSTREAM_URL` |

---

## 七、模块依赖关系

```
main.py
  ├── config.py
  ├── observability/health.py
  ├── observability/request_id.py
  ├── middleware/auth.py ──→ config.py
  ├── middleware/identity.py ──→ governance/api_keys.py ──→ storage/models.py
  ├── governance/key_provider.py ──→ governance/providers/{passthrough,static_key,oneapi_nanfu_yxai}.py
  ├── proxy/relay.py ────→ engine/scanner.py ────→ engine/rules_keyword.py
  │       │               │                   └─→ engine/rules_regex.py
  │       │               └─→ engine/models.py
  │       ├─→ proxy/fake_response.py ──→ engine/models.py
  │       ├─→ proxy/header_policy.py
  │       ├─→ proxy/stream.py
  │       ├─→ proxy/upstream_router.py
  │       ├─→ storage/archive.py ──→ storage/models.py ──→ storage/database.py
  │       └─→ storage/audit.py ────→ storage/models.py
  │
  └── admin/router.py ──→ admin/schemas.py
          ├─→ governance/api_keys.py
          ├─→ governance/key_provider.py
          ├─→ storage/admin_ops.py
          ├─→ storage/archive.py
          └─→ storage/audit.py
```

**依赖原则**

- 上层模块依赖下层模块，禁止反向依赖
- `proxy/` 可以依赖 `engine/`、`storage/`、`governance/` 透出的请求上下文，不直接依赖具体 Provider 实现
- `engine/` 不依赖 `proxy/`、`storage/`、`governance/`
- `storage/` 不依赖 `engine/`、`proxy/`、`governance/`
- `governance/providers/` 只封装中转站 Key 管理，不影响 relay/scanner/archive/audit 核心链路
- `notify/` 当前未接入主链路，阶段 8 启用后只依赖审计事件和脱敏后的扫描结果
- `admin/` 可依赖 `storage/` 和 `governance/` 服务层，不直接访问中转站资源权限体系
