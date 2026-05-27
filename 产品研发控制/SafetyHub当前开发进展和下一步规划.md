# LLM-SafetyHub 当前开发进展和下一步规划

> 更新时间：2026-05-27  
> 当前阶段：阶段 0 — 基础设施搭建  
> 当前状态：阶段 0 已完成，可进入阶段 1 核心安全链路开发

---

## 一、当前执行进展

本轮从空项目起步，按照 `SafetyHub实现阶段规划.md` 和 `SafetyHub代码结构框架规划.md` 完成了阶段 0 的工程初始化工作。项目已从仅包含规划文档的空目录，推进为具备 FastAPI 应用入口、配置加载、数据库初始化、健康检查、请求追踪、容器化配置和测试骨架的可运行工程。

### 1.1 已完成内容

| 类别 | 完成项 | 说明 |
|------|--------|------|
| 项目结构 | 创建核心目录结构 | 已创建 `proxy/`、`engine/`、`governance/`、`file_security/`、`observability/`、`storage/`、`admin/`、`notify/`、`middleware/`、`tests/`、`scripts/`、`nginx/` |
| 应用入口 | 创建 `main.py` | 使用 FastAPI 生命周期管理，启动时初始化数据库，退出时关闭数据库连接 |
| 配置管理 | 创建 `config.py` | 使用 `pydantic-settings` 读取 `.env`，覆盖上游、规则、数据库、管理员、Webhook、文件安全和 Uvicorn 配置 |
| 依赖注入 | 创建 `dependencies.py` | 预留统一配置依赖入口 |
| 健康检查 | 创建 `observability/health.py` | 提供 `/health/live` 和 `/health/ready` |
| 请求追踪 | 创建 `observability/request_id.py` | 自动生成或透传 `X-Request-ID` |
| 数据库基线 | 创建 `storage/database.py` | 使用 SQLAlchemy Async + aiosqlite，启动时自动创建表 |
| ORM 模型 | 创建 `storage/models.py` | 已预留消息归档、审计日志、管理员操作审计三类基础表 |
| 规则配置 | 创建 `engine/rules_config.yaml` | 当前为空规则版本，阶段 1 会扩展关键词与正则规则 |
| 管理前端占位 | 创建 `admin/static/` | 已提供最小 `index.html`、`style.css`、`app.js`，用于 Nginx 静态挂载验证 |
| 容器化 | 创建 `Dockerfile` 和 `docker-compose.yml` | 包含 FastAPI 服务和 Nginx 服务 |
| Nginx | 创建 `nginx/nginx.conf` | 已预留 `/health/`、`/v1/` 反向代理和 `/admin/` 静态资源挂载 |
| 本地工具 | 创建 `Makefile` | 提供安装、运行、测试、初始化数据库、Docker 启停命令 |
| 环境模板 | 创建 `.env.example` | 只包含示例配置，不包含真实密钥 |
| 忽略规则 | 创建 `.gitignore` | 忽略 `.env`、数据库、缓存、虚拟环境、证书等本地产物 |
| 初始化脚本 | 创建 `scripts/init_db.py` | 支持手动初始化数据库 |
| 测试骨架 | 创建 `tests/test_health.py` 和 `pytest.ini` | 覆盖健康检查和请求 ID 最小验证 |
| 虚拟环境 | 创建 `.venv` 并安装依赖 | 已使用项目专用虚拟环境安装 `requirements.txt` |
| 部署材料 | 创建 `项目部署/` | 已集中存放环境说明、直接部署说明、Docker 部署说明、环境模板和 PowerShell 脚本 |

---

## 二、验证结果

### 2.1 已执行验证

| 验证项 | 命令 | 结果 |
|--------|------|------|
| Python 语法编译检查 | `python -m compileall .` | 通过 |
| 安装项目依赖 | `python -m pip install -r requirements.txt` | 通过 |
| 单元测试 | `python -m pytest` | 通过，2 passed |
| 创建虚拟环境 | `python -m venv .venv` | 通过 |
| 虚拟环境安装依赖 | `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` | 通过 |
| 虚拟环境单元测试 | `.\.venv\Scripts\python.exe -m pytest` | 通过，2 passed |
| 部署验证脚本 | `.\项目部署\verify_venv.ps1` | 通过，2 passed |

### 2.2 当前可确认能力

- FastAPI 应用可以被测试客户端正常加载。
- 应用生命周期可以触发数据库初始化。
- `/health/live` 返回 `{"status": "ok"}`。
- `/health/ready` 返回数据库和规则文件检查结果。
- 响应头会自动带上 `X-Request-ID`。
- SQLite 数据目录会在初始化时自动创建。
- 阶段 0 的 Python 文件无语法错误。
- 项目根目录 `.venv` 已可用于本地运行和测试。
- `项目部署/` 已提供环境初始化、直接部署、Docker 部署和验证脚本。

---

## 三、与原规划的差异

| 原规划项 | 当前处理 | 差异原因 |
|----------|----------|----------|
| GitHub Actions CI | 暂未创建 | 当前仓库尚未确认远端 CI 环境；阶段 0 本地测试已先打通，CI 可在接入 GitHub 仓库后补充 |
| 数据库迁移版本机制 | 当前仅预留 `storage/migrations/` | 阶段 0 先使用 `Base.metadata.create_all` 建立运行基线；正式迁移工具建议在模型稳定后引入 Alembic |
| Nginx HTTPS / 自签证书 | 当前只提供 HTTP 配置 | 本地开发阶段先保证反向代理路径可用；TLS 证书和生产 HTTPS 属于阶段 3 部署加固 |
| 管理后台完整页面 | 当前只做静态占位首页 | 按规划，完整后台属于阶段 2；阶段 0 只验证静态资源目录和 Nginx 挂载结构 |
| 规则库初始内容 | 当前为空规则配置 | 关键词和正则规则属于阶段 1 检测引擎任务，当前只提供配置文件入口 |
| pip 升级 | 当前 `.venv` 安装依赖时不主动升级 pip | Windows 下首次尝试升级 pip 出现自替换中断，已重建 `.venv` 并改为直接安装依赖，当前验证通过 |

---

## 四、当前项目结构摘要

```text
NF-SafetyHub/
├── main.py
├── config.py
├── dependencies.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── pytest.ini
├── proxy/
├── engine/
│   └── rules_config.yaml
├── governance/
├── file_security/
├── observability/
│   ├── health.py
│   └── request_id.py
├── storage/
│   ├── database.py
│   ├── models.py
│   └── migrations/
├── admin/
│   └── static/
├── notify/
├── middleware/
├── scripts/
│   └── init_db.py
├── tests/
│   └── test_health.py
├── nginx/
│   └── nginx.conf
├── 项目部署/
│   ├── 环境与部署总览.md
│   ├── 直接部署说明.md
│   ├── Docker部署说明.md
│   ├── setup_venv.ps1
│   ├── run_dev.ps1
│   ├── deploy_direct.ps1
│   ├── deploy_docker.ps1
│   └── verify_venv.ps1
└── 项目落地/
```

---

## 五、下一步规划

下一步进入 **阶段 1：核心安全链路**。建议按照依赖关系优先做检测引擎，再做中继转发，最后接入归档。

### 5.1 阶段 1 第一批任务

| 优先级 | 任务 | 目标产出 |
|--------|------|----------|
| P0 | 实现 `engine/models.py` | 定义 `ScannerResult`、`AggregatedScanResult` |
| P0 | 实现 `engine/base.py` | 定义 Scanner 抽象基类 |
| P0 | 实现 `engine/normalizer.py` | 处理 Unicode、零宽字符、大小写等绕过基础防护 |
| P0 | 实现 `engine/scanner.py` | 完成扫描器链式调度，支持 block 早停和 warn 汇总 |
| P0 | 扩展 `engine/rules_config.yaml` | 增加初版关键词规则和正则规则 |
| P0 | 实现 `engine/rules_keyword.py` | 完成关键词规则检测 |
| P0 | 实现 `engine/rules_regex.py` | 完成正则规则检测 |
| P0 | 增加检测引擎测试 | 覆盖关键词、正则、调度器、归一化 |

### 5.2 阶段 1 第二批任务

| 优先级 | 任务 | 目标产出 |
|--------|------|----------|
| P0 | 实现 `proxy/header_policy.py` | 请求头透传与剥离策略 |
| P0 | 实现 `proxy/upstream_router.py` | 单上游转发和多上游接口预留 |
| P0 | 实现 `proxy/stream.py` | SSE 流式转发工具 |
| P0 | 实现 `proxy/fake_response.py` | 兼容 OpenAI Chat Completions 的伪装回复 |
| P0 | 实现 `proxy/relay.py` | `/v1/chat/completions` 中继入口，集成扫描和伪装回复 |
| P0 | 实现 `storage/archive.py` | 请求和响应归档写入能力 |
| P0 | 增加中继与伪装回复测试 | 覆盖流式、非流式、拦截、放行路径 |

### 5.3 阶段 1 验收目标

- 正常请求能通过 `/v1/chat/completions` 转发到上游。
- 命中 block 规则的请求不会发往上游，而是返回伪装回复。
- 命中 warn 规则的请求继续放行，并预留审计/告警记录入口。
- 流式请求可以逐 chunk 透传。
- 请求和响应可以写入 SQLite 归档表。
- 检测引擎单元测试通过。
- 中继和伪装回复测试通过。

---

## 六、当前注意事项

- 项目根目录已创建 `.venv`，本地运行、测试和直接部署优先使用 `.venv` 中的 Python。
- `.env.example` 和 `项目部署/.env.*.example` 都只是模板，正式运行前需要复制为 `.env` 并填写本地配置。
- 生产环境必须设置强 `ADMIN_PASSWORD` 和真实 `UPSTREAM_URL`，否则启动校验会拒绝生产启动。
- 当前 `engine/rules_config.yaml` 为空规则，仅用于阶段 0 ready 检查；阶段 1 必须补充实际规则。
- 当前数据库表通过 `create_all` 创建，适合启动期；后续模型稳定后应引入 Alembic 或等效迁移机制。
- Windows 环境下不建议在脚本中主动升级 `.venv` 内 pip；如需升级，建议单独手动执行并确认虚拟环境状态。
