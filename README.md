# LLM-SafetyHub

LLM 对话安全代理层 —— 部署在用户客户端与大模型中转站之间，对对话内容进行实时安全检测、拦截与归档。

## 功能概览

| 能力 | 说明 | 状态 |
|------|------|------|
| 透明中继 | 兼容 OpenAI API 格式，对客户端和中转站完全透明，支持流式/非流式 | 阶段 1 开发中 |
| 安全检测 | 关键词匹配 + 正则规则，命中时拦截请求并伪装为大模型正常回复 | 阶段 1 开发中 |
| 消息归档 | 全量记录 prompt 和 response，支持按用户/模型/时间查询 | 数据模型已就绪 |
| 审计追溯 | 拦截事件独立记录，含规则、匹配片段、执行动作 | 数据模型已就绪 |
| 实时告警 | 拦截事件推送至企业微信/飞书，支持静默与限流 | 阶段 2 规划中 |
| 管理后台 | Web 仪表盘：拦截记录、消息归档、规则管理、系统设置 | 阶段 2 规划中 |
| 治理预留 | APIKey 权限、模型访问策略、临时审批流程 | 数据结构已预留 |
| 文件安全 | 上传文件解析、检测、脱敏 | 阶段 3 规划中 |

## 架构

```
┌──────────┐     ┌──────────────────────────────────────┐     ┌──────────┐
│          │     │           LLM-SafetyHub              │     │          │
│  客户端   │────→│  中继转发 → 安全检测 → 伪装回复/放行  │────→│  中转站   │
│          │     │         ↓ 归档  ↓ 审计  ↓ 告警        │     │          │
└──────────┘     └──────────────────────────────────────┘     └──────────┘
```

## 项目结构

```
safetyhub/
├── main.py                  # FastAPI 应用入口
├── config.py                # 配置加载（pydantic-settings）
├── dependencies.py          # FastAPI 依赖注入
├── proxy/                   # 中继转发与伪装回复
├── engine/                  # 安全扫描引擎（关键词 + 正则）
│   └── rules_config.yaml    # 规则配置文件
├── governance/              # APIKey 权限、模型策略、审批（预留）
├── file_security/           # 文件安全检测（预留）
├── observability/           # 健康检查、请求追踪
├── storage/                 # 数据持久化（SQLAlchemy Async + SQLite）
│   ├── database.py
│   ├── models.py            # ORM 模型：消息归档、审计日志、管理员操作
│   └── migrations/
├── admin/                   # 管理后台（静态前端）
├── notify/                  # 告警通知（预留）
├── middleware/              # 中间件（预留）
├── nginx/                   # Nginx 反向代理配置
├── scripts/                 # 运维脚本
├── tests/                   # 测试
├── Dockerfile
├── docker-compose.yml
└── Makefile
```

## 快速开始

### 环境要求

- Python 3.12+
- Docker & Docker Compose（可选，用于容器化部署）

### 本地运行

```bash
# 1. 克隆仓库
git clone https://github.com/你的用户名/NF-SafetyHub.git
cd NF-SafetyHub

# 2. 创建虚拟环境并安装依赖
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt

# 3. 复制环境配置
cp .env.example .env
# 编辑 .env，至少填写 UPSTREAM_URL（中转站地址）

# 4. 启动服务
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 5. 验证
curl http://localhost:8000/health/live
# 返回 {"status":"ok"}
```

### Docker 部署

```bash
# 复制环境配置并编辑
cp .env.example .env

# 启动
docker compose up --build

# 验证
curl http://localhost:8000/health/live
```

### 常用命令

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

关键配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `UPSTREAM_URL` | 中转站地址（生产环境必填） | 空 |
| `DB_URL` | 数据库连接字符串 | `sqlite+aiosqlite:///./data/safetyhub.db` |
| `ADMIN_PASSWORD` | 管理员密码（生产环境需 ≥12 位） | 空 |
| `RULES_CONFIG_PATH` | 规则配置文件路径 | `engine/rules_config.yaml` |
| `WEBHOOK_URL` | 告警推送地址 | 空 |
| `ENVIRONMENT` | 运行环境 `development` / `production` | `development` |

生产环境启动时会校验必要配置，缺失或弱密码会导致启动失败。

## 健康检查

| 端点 | 说明 |
|------|------|
| `GET /health/live` | 进程存活检查 |
| `GET /health/ready` | 就绪检查（数据库 + 规则文件） |

## 开发阶段

| 阶段 | 内容 | 版本 | 状态 |
|------|------|------|------|
| 阶段 0 | 基础设施搭建 | v0.1 | ✅ 已完成 |
| 阶段 1 | 核心安全链路（中继+检测+归档+伪装） | v0.5 | 🔧 进行中 |
| 阶段 2 | 管理能力完善（后台+审计+告警） | v0.8 | 📋 规划中 |
| 阶段 3 | 打磨上线（测试+部署加固） | v1.0 | 📋 规划中 |

## 分支策略

| 分支 | 用途 | 保护 |
|------|------|------|
| `main` | 生产分支，仅接受来自 staging 的 PR | 受保护，需审核 |
| `staging` | 验证分支，集成测试通过后合并到 main | 受保护，需审核 |
| `dev` | 开发分支，日常开发合并目标 | 开放 push |
| `feature/*` | 功能分支，从 dev 创建 | 开放 push |

## 技术栈

- **Web 框架**：FastAPI + Uvicorn
- **数据库**：SQLAlchemy (Async) + aiosqlite (SQLite)
- **配置**：pydantic-settings
- **HTTP 客户端**：httpx（用于上游中继）
- **容器化**：Docker + Nginx
- **测试**：pytest + pytest-asyncio

## 许可证

私有项目，未授权禁止使用。
