# LLM-SafetyHub 代码结构框架规划

> 本文档定义项目的代码结构、模块职责、接口规范和数据流，为团队开发提供明确的代码级指引。

---

## 一、项目目录结构

```
safetyhub/
├── main.py                          # FastAPI 应用入口
├── config.py                        # 配置加载（YAML + 环境变量 + 热加载）
├── dependencies.py                  # FastAPI 依赖注入
│
├── proxy/                           # [核心层] 中继与伪装
│   ├── __init__.py
│   ├── relay.py                     # 核心中继转发引擎
│   ├── fake_response.py             # 伪装回复生成器
│   ├── header_policy.py             # Header 透传/剥离策略
│   ├── upstream_router.py           # APIKey/模型到上游的路由预留
│   └── stream.py                    # SSE 流式处理工具
│
├── engine/                          # [检测层] 安全扫描引擎
│   ├── __init__.py
│   ├── scanner.py                   # 扫描器调度引擎（链式调用）
│   ├── base.py                      # Scanner 抽象基类
│   ├── normalizer.py                # 文本归一化与绕过防护
│   ├── rules_keyword.py             # 关键词规则 Scanner
│   ├── rules_regex.py               # 正则规则 Scanner
│   ├── rules_config.yaml            # 规则配置文件
│   └── models.py                    # ScannerResult 等数据模型
│
├── governance/                      # [治理层] 身份、权限与审批预留
│   ├── __init__.py
│   ├── identity.py                  # 用户/APIKey 身份解析
│   ├── api_keys.py                  # APIKey 元数据与权限预留
│   ├── model_policy.py              # 模型访问策略预留
│   └── approval.py                  # 临时放行审批流程预留
│
├── file_security/                   # [文件安全] 上传文件解析与检测预留
│   ├── __init__.py
│   ├── extractor.py                 # PDF/Office/TXT 等文本抽取
│   ├── sanitizer.py                 # 文件内容脱敏与重写预留
│   └── router.py                    # 文件上传/解析接口预留
│
├── observability/                   # [可观测性] 健康检查、指标与追踪
│   ├── __init__.py
│   ├── health.py                    # live/ready 健康检查
│   ├── metrics.py                   # 请求、扫描、上游、告警指标
│   └── request_id.py                # X-Request-ID 生成与透传
│
├── storage/                         # [存储层] 数据持久化
│   ├── __init__.py
│   ├── database.py                  # 异步数据库连接管理
│   ├── migrations/                  # 数据库迁移脚本
│   ├── models.py                    # SQLAlchemy ORM 模型
│   ├── archive.py                   # 消息归档 CRUD
│   ├── audit.py                     # 审计日志 CRUD
│   ├── retention.py                 # 数据保留与清理任务
│   └── admin_ops.py                 # 管理员操作审计 CRUD
│
├── admin/                           # [管理层] 管理后台
│   ├── __init__.py
│   ├── router.py                    # 管理后台 API 路由
│   ├── schemas.py                   # Pydantic 请求/响应模型
│   └── static/                      # 管理员前端静态文件
│       ├── index.html               # 仪表盘
│       ├── blocks.html              # 拦截记录
│       ├── archives.html            # 消息归档
│       ├── rules.html               # 规则管理
│       ├── approvals.html           # 临时审批记录预留
│       ├── api_keys.html            # APIKey/模型权限管理预留
│       ├── settings.html            # 系统设置
│       ├── css/
│       │   └── style.css
│       └── js/
│           └── app.js
│
├── notify/                          # [通知层] 告警推送
│   ├── __init__.py
│   ├── webhook.py                   # 企微/飞书 Webhook 推送
│   ├── approval_webhook.py          # 交互式审批通知预留
│   └── rate_limiter.py              # 告警频率控制
│
├── middleware/                      # [中间件层]
│   ├── __init__.py
│   ├── auth.py                      # 管理后台认证
│   ├── identity.py                  # 用户/APIKey 身份注入
│   ├── request_limit.py             # 请求大小与并发限制
│   ├── logging.py                   # 请求日志（脱敏）
│   └── error_handler.py             # 全局异常处理
│
├── tests/                           # [测试]
│   ├── __init__.py
│   ├── conftest.py                  # pytest fixtures
│   ├── test_relay.py                # 中继转发测试
│   ├── test_scanner.py              # 扫描引擎测试
│   ├── test_keyword.py              # 关键词规则测试
│   ├── test_regex.py                # 正则规则测试
│   ├── test_archive.py              # 消息归档测试
│   ├── test_fake_response.py        # 伪装回复测试
│   ├── test_audit.py                # 审计日志测试
│   ├── test_webhook.py              # 告警推送测试
│   └── test_e2e.py                  # 端到端集成测试
│
├── nginx/                           # [部署] Nginx 配置
│   ├── nginx.conf
│   └── ssl/                         # TLS 证书（.gitignore）
│
├── scripts/                         # [运维] 辅助脚本
│   ├── init_db.py                   # 数据库初始化
│   └── seed_rules.py                # 规则种子数据
│
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## 二、核心模块详细设计

### 2.1 `main.py` — 应用入口

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from config import settings
from proxy.relay import router as relay_router
from admin.router import router as admin_router
from middleware.auth import AdminAuthMiddleware
from middleware.logging import RequestLoggingMiddleware
from middleware.error_handler import register_exception_handlers
from storage.database import init_db, close_db
from engine.scanner import ScannerOrchestrator
from engine.rules_keyword import KeywordScanner
from engine.rules_regex import RegexScanner
from notify.webhook import WebhookNotifier


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scanner = ScannerOrchestrator()
    scanner.register(KeywordScanner(settings.rules_config_path))
    scanner.register(RegexScanner(settings.rules_config_path))
    app.state.scanner = scanner
    app.state.notifier = WebhookNotifier(settings.webhook_url)
    yield
    await close_db()


app = FastAPI(
    title="LLM-SafetyHub",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(AdminAuthMiddleware)
app.add_middleware(RequestLoggingMiddleware)
register_exception_handlers(app)

app.include_router(relay_router, prefix="/v1")
app.include_router(admin_router, prefix="/admin")
```

**职责**

- FastAPI 应用创建和生命周期管理
- 中间件注册
- 路由注册
- Scanner 和 Notifier 的初始化和注入

---

### 2.2 `config.py` — 配置管理

```python
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    app_name: str = "LLM-SafetyHub"
    debug: bool = False

    upstream_url: str                          # 默认中转站地址
    upstream_timeout_connect: int = 10         # 连接超时(秒)
    upstream_timeout_read: int = 120           # 读取超时(秒)
    upstream_route_config_path: Path = Path("config/upstream_routes.yaml")

    rules_config_path: Path = Path("engine/rules_config.yaml")
    rules_reload_interval: int = 5             # 规则热加载间隔(秒)
    scanner_order: list[str] = ["keyword", "regex"]

    db_url: str = "sqlite+aiosqlite:///./data/safetyhub.db"
    archive_retention_days: int = 180
    audit_retention_days: int = 365
    data_encryption_enabled: bool = False
    data_encryption_key_env: str = "SAFETYHUB_DATA_KEY"

    admin_username: str = "admin"
    admin_password: str                         # 环境变量注入
    admin_ip_whitelist: list[str] = []

    webhook_url: str = ""
    webhook_type: str = "wecom"                 # wecom / feishu
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
- APIKey 与模型权限配置先预留文件和数据结构，v1.0 默认走单上游，v1.1 后逐步启用多上游和细粒度授权
- 数据保留、文件扫描、临时审批默认可关闭，避免 MVP 阶段扩大实现范围

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
from notify.webhook import WebhookNotifier

router = APIRouter()


@router.post("/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    is_stream = body.get("stream", False)
    user_id = extract_user_id(request)

    scan_result = await request.app.state.scanner.scan(
        extract_text_from_messages(body.get("messages", []))
    )

    if scan_result.blocked:
        await record_audit_and_alert(request, scan_result, user_id)
        return await generate_fake_response(body, scan_result, is_stream)

    if is_stream:
        return await relay_stream(request, body, user_id, scan_result)
    else:
        return await relay_non_stream(request, body, user_id, scan_result)


async def relay_stream(request, body, user_id, scan_result):
    ...


async def relay_non_stream(request, body, user_id, scan_result):
    ...


def extract_text_from_messages(messages: list) -> str:
    ...


def extract_user_id(request: Request) -> str:
    ...
```

**核心流程**

```
请求到达
  │
  ├─ 提取 messages 文本
  │
  ├─ Scanner 扫描
  │     │
  │     ├─ blocked → 审计记录 + 告警推送 + 返回伪装回复
  │     │
  │     └─ passed → 转发到中转站
  │                   │
  │                   ├─ 流式：SSE 逐 chunk 透传
  │                   └─ 非流式：JSON 透传
  │
  └─ 异步归档（不阻塞响应）
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
    prompt = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    is_stream = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    blocked_rule_id = Column(String(64), nullable=True)
    approval_id = Column(String(64), nullable=True, index=True)
    file_ids = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    completed_at = Column(DateTime, nullable=True)
    latency_ms = Column(Integer, nullable=True)

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
    owner_user_id = Column(String(128), nullable=False, index=True)
    owner_department = Column(String(128), nullable=True, index=True)
    status = Column(String(16), default="active", index=True)
    allowed_models = Column(Text, nullable=True)
    allowed_capabilities = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    expires_at = Column(DateTime, nullable=True)


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

    @staticmethod
    async def export(
        start_time=None,
        end_time=None,
        format: str = "csv",
    ) -> str | bytes:
        ...
```

---

### 2.8 `admin/` — 管理后台

管理员前端属于本项目交付物，放在 `admin/static/` 目录中，由 Nginx 直接托管静态文件，后端仅提供 `/admin/api/*` 管理接口。v1.0 前端至少包含仪表盘、拦截记录、消息归档、规则查看、系统设置；APIKey/模型权限、审批记录页面先放置入口与只读占位，后续版本启用编辑能力。

#### 2.8.1 `admin/router.py` — API 路由

```python
from fastapi import APIRouter, Depends, Query
from admin.schemas import *
from storage.archive import ArchiveReader
from storage.audit import AuditReader

router = APIRouter()


@router.get("/api/archives", response_model=ArchiveListResponse)
async def list_archives(
    user_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    ...


@router.get("/api/archives/{record_id}", response_model=ArchiveDetailResponse)
async def get_archive(record_id: int):
    ...


@router.get("/api/audits", response_model=AuditListResponse)
async def list_audits(
    user_id: str | None = None,
    rule_id: str | None = None,
    rule_level: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    ...


@router.get("/api/audits/{record_id}", response_model=AuditDetailResponse)
async def get_audit(record_id: int):
    ...


@router.get("/api/audits/export")
async def export_audits(
    start_time: str | None = None,
    end_time: str | None = None,
    format: str = "csv",
):
    ...


@router.get("/api/stats", response_model=StatsResponse)
async def get_stats():
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

#### 2.9.1 `notify/webhook.py`

```python
import httpx
from engine.models import ScannerResult
from notify.rate_limiter import AlertRateLimiter


class WebhookNotifier:
    def __init__(self, webhook_url: str, webhook_type: str = "wecom"):
        self._url = webhook_url
        self._type = webhook_type
        self._limiter = AlertRateLimiter()

    async def notify(self, result: ScannerResult, user_id: str, request_id: str) -> None:
        if not self._url:
            return
        if not self._limiter.should_send(result.rule_id, user_id):
            return
        payload = self._build_payload(result, user_id, request_id)
        try:
            async with httpx.AsyncClient() as client:
                await client.post(self._url, json=payload, timeout=5)
        except httpx.HTTPError:
            pass

    def _build_payload(self, result: ScannerResult, user_id: str, request_id: str) -> dict:
        if self._type == "wecom":
            return self._build_wecom_payload(result, user_id, request_id)
        else:
            return self._build_feishu_payload(result, user_id, request_id)

    def _build_wecom_payload(self, result, user_id, request_id) -> dict:
        ...

    def _build_feishu_payload(self, result, user_id, request_id) -> dict:
        ...
```

#### 2.9.2 `notify/rate_limiter.py`

```python
import time
from collections import defaultdict


class AlertRateLimiter:
    def __init__(
        self,
        rule_silence_minutes: int = 5,
        user_silence_minutes: int = 2,
        hourly_limit: int = 50,
    ):
        self._rule_silence = rule_silence_minutes * 60
        self._user_silence = user_silence_minutes * 60
        self._hourly_limit = hourly_limit
        self._rule_last_sent: dict[str, float] = {}
        self._user_last_sent: dict[str, float] = {}
        self._hourly_count = 0
        self._hour_start = time.time()

    def should_send(self, rule_id: str, user_id: str) -> bool:
        now = time.time()
        if now - self._hour_start > 3600:
            self._hourly_count = 0
            self._hour_start = now
        if self._hourly_count >= self._hourly_limit:
            return False
        rule_key = rule_id
        if rule_key in self._rule_last_sent and now - self._rule_last_sent[rule_key] < self._rule_silence:
            return False
        user_key = f"{rule_id}:{user_id}"
        if user_key in self._user_last_sent and now - self._user_last_sent[user_key] < self._user_silence:
            return False
        self._rule_last_sent[rule_key] = now
        self._user_last_sent[user_key] = now
        self._hourly_count += 1
        return True
```

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

#### 2.10.2 `middleware/logging.py`

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import logging
import time

logger = logging.getLogger("safetyhub")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response
```

---

### 2.11 `governance/` — 身份、权限与审批预留

| 模块 | 职责 | v1.0 行为 | 后续启用方向 |
|------|------|-----------|--------------|
| `identity.py` | 解析用户、APIKey、来源 IP、客户端标识 | 统一生成 `RequestContext`，写入日志/归档/审计 | 接入企业 SSO、JWT claims、APIKey 归属映射 |
| `api_keys.py` | APIKey 元数据、状态、所属用户/部门 | 只存储哈希和只读占位，不做复杂授权 | 支持 APIKey 启停、额度、模型 allowlist |
| `model_policy.py` | 模型权限策略 | 默认允许配置中的模型集合 | 支持按用户/APIKey/部门控制模型、上下文长度、工具调用 |
| `approval.py` | 临时审批流程 | 预留数据模型和接口，不阻塞主链路 | 支持敏感请求人工审批后一次性放行 |

**预留原则**

- APIKey 永不明文入库，只存哈希、前后缀展示、创建时间、状态、归属信息
- 模型权限采用 `user_id + api_key_id + model + capability` 四元组预留，避免后续重构
- capability 至少预留 `chat`、`vision`、`file_upload`、`function_call`、`mcp_tool`、`reasoning`、`embedding`
- v1.0 不实现复杂权限决策，但 `RequestContext`、数据库字段和审计字段必须提前带上 `api_key_id`、`model`、`capability`

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
      - ./data:/app/data
      - ./engine/rules_config.yaml:/app/engine/rules_config.yaml:ro
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
  ├── proxy/relay.py ────→ engine/scanner.py ────→ engine/rules_keyword.py
  │       │               │                   └─→ engine/rules_regex.py
  │       │               └─→ engine/models.py
  │       ├─→ proxy/fake_response.py ──→ engine/models.py
  │       ├─→ proxy/stream.py
  │       ├─→ storage/archive.py ──→ storage/models.py ──→ storage/database.py
  │       ├─→ storage/audit.py ────→ storage/models.py
  │       └─→ notify/webhook.py ──→ notify/rate_limiter.py
  │
  ├── admin/router.py ──→ admin/schemas.py
  │       ├─→ storage/archive.py
  │       └─→ storage/audit.py
  │
  ├── middleware/auth.py ──→ config.py
  ├── middleware/logging.py
  └── middleware/error_handler.py
```

**依赖原则**

- 上层模块依赖下层模块，禁止反向依赖
- `proxy/` 可以依赖 `engine/`、`storage/`、`notify/`
- `engine/` 不依赖 `proxy/`、`storage/`、`notify/`
- `storage/` 不依赖 `engine/`、`proxy/`、`notify/`
- `notify/` 只依赖 `engine/models.py`（数据模型）
- `admin/` 只依赖 `storage/`
