# LLM-SafetyHub

LLM 对话安全代理层，部署在用户客户端与大模型中转站之间，提供 OpenAI-compatible `/v1/*` 透明中继、请求侧安全检测、拦截伪装、归档审计、APIKey 治理和单实例 Docker 生产稳定性保护。

当前阶段：**阶段 6A — 单实例 Docker 生产稳定性与高并发治理**。阶段 1~6 核心能力已落地，阶段 6A 工程能力已落地并进入生产压测、真实上游联调和运维验收阶段；阶段 7 及之后能力暂不开发，仅保留长期规划。

## 功能概览

| 能力 | 说明 | 状态 |
|------|------|------|
| 透明中继 | 兼容 OpenAI API `/v1/*`，支持 Chat、Embeddings、Completions、Responses、Images、未知端点和 `GET /v1/models` 默认透传 | ✅ 已完成 |
| 字节级透传 | 未脱敏路径使用原始 `raw_body` 转发，保留 JSON key 顺序、空白、编码和非严格未知端点兼容性 | ✅ 已完成 |
| 安全检测 | 关键词 + 正则扫描；Chat 默认扫描最新允许 role 的文本消息；手机号请求侧脱敏，保守关键词 block | ✅ 已完成 |
| 伪装回复 | 命中 block 规则时返回 OpenAI Chat Completions 兼容伪装回复，不触达上游 | ✅ 已完成 |
| 消息归档 | Chat 非流式/流式 prompt 与 response 归档，保留原始 prompt 与脱敏后 prompt | ✅ 已完成 |
| 图片资产归档 | 文生图元数据归档，URL / b64 图片本体异步归档并记录状态 | ✅ 已完成 |
| 审计追溯 | block / desensitize 命中事件写入审计日志，支持后台分页筛选和详情查看 | ✅ 已完成 |
| 管理后台 | 静态 HTML + 原生 JS 后台，支持登录、仪表盘、归档、审计、观测、规则、APIKey、运行状态 | ✅ 已完成 |
| APIKey 治理 | K-Sync 默认、加密存储、有效性校验、上游 Key 替换、reveal、吊销、CSV 批量替换 | ✅ 已完成 |
| KeyProvider | 支持 `passthrough`、`static`、`oneapi_nanfu_yxai` Provider 创建、获取完整 Key 和吊销 | ✅ 核心能力已完成 |
| 高并发治理 | `/v1/*` 有界并发队列、排队超时、队列满 429、共享上游连接池、归档队列削峰、后台统计缓存 | 🔄 工程能力已落地，待生产压测验收 |
| 实时告警 | Webhook 告警、告警限流、审计导出 | ⏸️ 阶段 8 长期规划 |
| 文件安全 | 文件解析、扫描、脱敏、文件安全后台 | ⏸️ 阶段 10 长期规划 |

## 架构

```text
┌──────────┐     ┌──────────────────────────────────────────────────────────────┐     ┌──────────┐
│          │     │                       LLM-SafetyHub                         │     │          │
│  客户端   │────→│  /v1 中继 → 身份/APIKey → 安全检测 → 脱敏/伪装/透传 → 归档审计  │────→│  中转站   │
│          │     │      ↑ 并发队列 / 请求体限制 / 共享连接池 / 后台队列削峰        │     │          │
└──────────┘     └──────────────────────────────────────────────────────────────┘     └──────────┘
```

## 项目结构

```text
NF-SafetyHub/
├── main.py                    # FastAPI 应用入口、生命周期、共享资源初始化
├── config.py                  # pydantic-settings 配置和生产启动校验
├── proxy/                     # OpenAI-compatible 中继、Header 策略、SSE 流式、伪装回复
├── engine/                    # 关键词/正则扫描、规则配置、调度引擎
├── governance/                # APIKey 服务、KeyProvider 抽象与 Provider 实现
├── middleware/                # 管理认证、APIKey 身份、请求体限制、/v1 并发队列
├── runtime/                   # 上游共享 HTTP client、归档队列、后台统计缓存
├── storage/                   # SQLAlchemy Async 模型、数据库、归档、审计、图片资产
├── admin/                     # 管理 API 与静态后台页面
├── observability/             # 健康检查、Request ID
├── file_security/             # 文件安全长期规划占位
├── notify/                    # 告警通知长期规划占位
├── nginx/                     # Nginx 反向代理配置
├── scripts/                   # 初始化、迁移、导入、验证脚本
├── tests/                     # 自动化测试
├── verify/                    # 手动联调脚本
├── 交付运行手册/              # 生产/内网部署说明与脚本
├── 产品研发控制/              # 研发规划、进展、测试验证文档
├── docker离线部署/            # Docker 离线部署包制作脚本与材料
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── requirements.txt
└── pytest.ini
```

## 快速开始

### 环境要求

- Python 3.12+
- Docker & Docker Compose（生产/容器化部署推荐）
- PostgreSQL（生产推荐，`docker-compose.yml` 已包含 PostgreSQL 服务）

### 本地运行

```bash
# 1. 创建虚拟环境并安装依赖
python -m venv .venv

# Windows
.\.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt

# 2. 复制环境配置
cp .env.example .env

# 3. 编辑 .env，至少设置开发联调所需配置
# UPSTREAM_URL=<中转站地址>
# ADMIN_PASSWORD=<管理员密码>

# 4. 启动开发服务
uvicorn main:app --host 0.0.0.0 --port 8000

# 5. 验证
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

开发环境可使用 SQLite 默认配置；生产环境必须按生产安全要求设置 `ENVIRONMENT=production`、`ADMIN_PASSWORD`、`SAFETYHUB_DATA_KEY`、`UPSTREAM_URL`，并关闭空 APIKey 透传。

### Docker 部署

```bash
# 1. 复制并编辑生产配置
cp 交付运行手册/.env.production.example .env

# 2. 启动 PostgreSQL + SafetyHub + Nginx
docker compose up --build -d

# 3. 验证
curl http://127.0.0.1/health/live
curl http://127.0.0.1/health/ready
```

Dockerfile 使用多 worker 生产启动命令：`uvicorn main:app --workers ${UVICORN_WORKERS:-4}`，不使用 `--reload`。

## 阶段 6A 生产配置建议

阶段 6A 当前按单实例 Docker、4 worker 生产场景设计，目标覆盖容器总 `1000` in-flight + `2000` 排队。若 worker 数变化，需要同步折算每 worker 配置。

```text
UVICORN_WORKERS=4
V1_MAX_INFLIGHT=250
V1_MAX_QUEUE_SIZE=500
V1_QUEUE_TIMEOUT_SECONDS=15
UPSTREAM_MAX_CONNECTIONS=200
UPSTREAM_MAX_KEEPALIVE_CONNECTIONS=100
UPSTREAM_TIMEOUT_POOL=5
ADMIN_STATS_CACHE_SECONDS=10
ARCHIVE_QUEUE_MAX_SIZE=5000
ARCHIVE_BATCH_SIZE=50
ARCHIVE_FLUSH_INTERVAL_SECONDS=1
ARCHIVE_MAX_PAYLOAD_BYTES=262144
```

`/admin/*`、`/admin/api/*`、`/health/*` 不进入 `/v1/*` 并发队列，压测期间仍应持续验证管理端和健康检查可用性。

## 离线部署包打包

离线交付分两层打包：先生成 SafetyHub 应用与镜像 bundle，再生成包含 Docker、Docker Compose 和应用 bundle 的整体离线部署包。

```bash
# 1. 生成最新 SafetyHub 内网应用 bundle
bash 交付运行手册/build_intranet_offline_bundle.sh

# 2. 生成整体 Docker 离线部署包
bash docker离线部署/scripts/prepare-offline-package.sh
```

最终交付文件会输出到 `docker离线部署/部署文件/`，包括 `docker-offline-deploy_*.tar.gz` 和对应的 `.sha256` 校验文件。

注意：`prepare-offline-package.sh` 会同步 `内网离线部署包/` 下最新的 `safetyhub_intranet_bundle_*.tar.gz`，并校验关键部署文件是否与当前源码一致。如果修改过 `docker-compose.yml`、`nginx/nginx.conf` 或部署脚本，必须先重新执行 `build_intranet_offline_bundle.sh`，否则整体打包会提前失败，避免旧 bundle 被误打进离线包。

## 常用命令

```bash
make install      # 安装依赖
make run          # 启动开发服务器
make test         # 运行测试
make init-db      # 初始化数据库
make docker-up    # Docker 启动
make docker-down  # Docker 停止
```

## 配置说明

所有配置通过 `.env` 文件或环境变量加载，完整配置项见 [.env.example](.env.example)。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ENVIRONMENT` | 运行环境，生产设置为 `production` | `development` |
| `UPSTREAM_URL` | 默认中转站地址，生产环境必填 | 空 |
| `DB_URL` | 数据库连接字符串，生产推荐 PostgreSQL | `sqlite+aiosqlite:///./data/safetyhub.db` |
| `ADMIN_PASSWORD` | 管理员密码，生产环境需 ≥12 位 | 空 |
| `SAFETYHUB_DATA_KEY` | APIKey 加密密钥环境变量，生产环境必填 | 空 |
| `ALLOW_EMPTY_API_KEYS_PASSTHROUGH` | APIKey 表为空时是否允许历史透传，生产应关闭 | `true` |
| `RULES_CONFIG_PATH` | 规则配置文件路径 | `engine/rules_config.yaml` |
| `SCANNER_FAIL_OPEN` | 扫描器异常时是否降级放行；生产建议保持关闭 | `false` |
| `KEY_PROVIDER_TYPE` | KeyProvider 类型：`passthrough` / `static` / `oneapi_nanfu_yxai` | `passthrough` |
| `REQUEST_MAX_BODY_MB` | 请求体大小限制 | `20` |
| `V1_MAX_INFLIGHT` | 每 worker `/v1/*` 最大在途请求数 | `150` |
| `V1_MAX_QUEUE_SIZE` | 每 worker `/v1/*` 最大排队请求数 | `200` |
| `ARCHIVE_QUEUE_MAX_SIZE` | 归档/审计后台队列上限 | `5000` |

生产环境启动时会校验关键配置，缺失或不安全配置会导致启动失败。

## 主要接口

| 端点 | 说明 |
|------|------|
| `GET /health/live` | 进程存活检查 |
| `GET /health/ready` | 就绪检查（数据库 + 规则文件） |
| `/v1/*` | OpenAI-compatible 通用代理入口 |
| `GET /admin/` | 管理后台静态页面入口 |
| `POST /admin/api/login` | 管理后台登录 |
| `GET /admin/api/stats` | 后台统计概览，阶段 6A 支持短缓存 |
| `GET /admin/api/runtime` | worker、并发队列、归档队列、上游连接池和磁盘状态快照 |
| `GET /admin/api/archives` | 消息归档分页查询 |
| `GET /admin/api/audits` | 审计日志分页查询 |
| `GET /admin/api/observations/recent` | 最近少量完整 Chat 样本观测 |
| `GET /admin/api/rules` | 规则列表 |
| `PATCH /admin/api/rules/{id}` | 启停规则并触发热加载 |
| `POST /admin/api/rules/reload` | 手动规则热加载 |
| `GET /admin/api/api-keys` | APIKey 列表 |
| `POST /admin/api/api-keys` | 手动或 Provider 创建 APIKey |
| `POST /admin/api/api-keys/{id}/reveal` | 受审计 reveal 完整 SafetyHub Key |
| `POST /admin/api/api-keys/{id}/replace-upstream-key` | 单条替换上游 Key |
| `POST /admin/api/api-keys/bulk-replace-upstream-keys` | CSV 批量替换上游 Key |

以下接口属于后续增强或阶段 8 规划，当前未实现：`GET /admin/api/settings`、`GET /admin/api/rules/top`、`GET /admin/api/audits/export`、`POST /admin/api/webhook/test`。

## 测试与验证

```bash
python -m pytest
```

历史固定通过数不再作为上线依据；生产上线判断以当前环境复跑、专项测试、Docker/真实上游联调和压测验收为准。数据库初始化会写入 `schema_migrations` 基线版本，用于后续版本化迁移追踪。

常用专项测试：

```bash
pytest tests/test_concurrency_limit.py
pytest tests/test_request_limit.py tests/test_scanner.py tests/test_models.py
pytest tests/test_api_keys.py
pytest tests/test_image_assets.py tests/test_relay_image_assets.py tests/test_admin_image_assets.py
pytest tests/test_relay.py tests/test_header_policy.py
```

更多验证方法见 `产品研发控制/SafetyHub测试验证指导.md`。

## 开发阶段

| 阶段 | 内容 | 状态 |
|------|------|------|
| 阶段 1 | 透传中继 + 健康检查 | ✅ 已完成 |
| 阶段 2 | 弱扫描 MVP（手机号脱敏 + 保守关键词 block + 规则热加载） | ✅ 已完成 |
| 阶段 3 | 归档 + 审计 + 文生图图片资产归档 | ✅ 已完成 |
| 阶段 4 | 管理员认证 + 最小后台 | ✅ 已完成 |
| 阶段 5 | APIKey 管理（K-Sync、加密、上游 Key 替换） | ✅ 已完成 |
| 阶段 6 | KeyProvider 抽象 + 中转站联通 | ✅ 核心能力已完成 |
| 阶段 6A | 单实例 Docker 生产稳定性与高并发治理 | 🔄 工程能力已落地，待生产压测验收 |
| 阶段 7 | 扫描升级 | ⏸️ 暂不开发，仅保留规划 |
| 阶段 8 | 可观测性增强 + 告警 | ⏸️ 暂不开发，仅保留规划 |
| 阶段 9 | 临时审批 + 安全策略 + 审批链 | ⏸️ 暂不开发，仅保留规划 |
| 阶段 10 | 远期能力（文件安全、NER、多上游、多租户等） | ⏸️ 暂不开发，仅保留规划 |

## 当前边界

- 真实 Docker 生产高并发阶梯压测、连接池观测、PostgreSQL 长时间运行、备份恢复和运维安全复核仍需生产环境验收。
- 替换上游 Key 后不会自动触达上游验证新 Key，也不会自动回滚；如新 Key 错误，需要管理员再次替换。
- 图片资产后台预览/下载页面、存储配额、保留策略和清理任务仍属阶段 8 规划。
- Webhook 告警、审计导出、临时审批运行链路、文件安全、NER、多上游、多租户暂不开发。

## 技术栈

- **Web 框架**：FastAPI + Uvicorn
- **数据库**：SQLAlchemy Async + SQLite（开发默认）/ PostgreSQL（生产推荐）
- **配置**：pydantic-settings
- **HTTP 客户端**：httpx（共享上游连接池与流式中继）
- **前端**：静态 HTML + 原生 JavaScript + CSS
- **容器化**：Docker + Docker Compose + Nginx
- **测试**：pytest + pytest-asyncio

## 许可证

私有项目，未授权禁止使用。
