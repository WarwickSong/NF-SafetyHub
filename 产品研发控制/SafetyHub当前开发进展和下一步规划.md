# LLM-SafetyHub 当前开发进展和下一步规划

> 更新时间：2026-06-05
> 当前阶段：阶段 6A — 单实例 Docker 生产稳定性与高并发治理
> 当前状态：阶段 1 OpenAI-compatible `/v1/*` 透传中继与健康检查已完成；阶段 2 弱扫描 MVP 已完成；阶段 3 归档 + 审计已完成；阶段 4 管理员认证 + 最小后台框架已完成；阶段 5 APIKey 管理已完成；阶段 6 已完成 KeyProvider 抽象、`passthrough` / `static` / `oneapi_nanfu_yxai` Provider、后台 Provider 创建、完整 Key 按需 reveal/复制、Provider-aware 吊销、`.env` 配置、既有 yxai Key JSON 导入脚本和历史 Key 导入。当前运行配置已从 SQLite 切换到 PostgreSQL，`api_keys` 已完成 SQLite 到 PostgreSQL 迁移并验证 `sqlite=23 postgres=23 OK`，`run_dev.sh` 启动后 `/health/ready` 返回数据库与规则检查通过。阶段 7 及之后的开发暂不进行，后续只保留规划记录；当前所有开发与验证优先级统一收敛到阶段 6A：在短期单实例 Docker 生产部署前提下，补齐 `/v1/*` 全局有界并发队列、生产启动方式、管理端保护、上游连接池复用、审计归档削峰和 PostgreSQL 运行稳定性验证；结合 100 名员工同时使用 OpenClaw/Hermes/批量标注 Agent 的峰值生产场景，生产目标至少支持容器总 `1000` in-flight + `2000` 排队，并允许通过 `.env` 或等价部署配置调整；流式与非流式统一纳入 `/v1/*` 队列，不单独拆分并发池。APIKey 的模型权限、token 额度、资源能力权限统一由中转站作为权威系统管理，SafetyHub 只做安全治理和上游 Key 映射。

---

## 一、实际代码状态

本状态基于当前仓库代码检查与测试结果。当前代码已经具备 FastAPI 应用入口、健康检查、Request ID、OpenAI-compatible `/v1/*` 通用中继转发、Header 安全透传、单上游路由、Scanner 调度、关键词/正则扫描、block 拦截伪装回复、请求侧手机号脱敏改写转发、SSE 透传与完整流式归档、规则定时热加载、管理后台规则启停和手动热加载、管理 API 和静态页面 Basic Auth + IP 白名单、Chat 归档/审计写入、正式归档/审计分页筛选和详情 API、统计概览 API、管理员操作审计、最小静态后台、文生图元数据归档、文生图图片本体异步归档、图片资产状态 API、最近对话观测 API、SQLite 旧表缺列补齐、PostgreSQL 运行配置、SQLite 到 PostgreSQL 迁移/验证脚本、R1~R9 schema 预留和 timezone-aware UTC 时间字段。

阶段 5 已新增 `governance/api_keys.py`、`middleware/identity.py`、后台 APIKey CRUD 接口和 `admin/static/api_keys.html` 可操作页面。SafetyHub 当前支持管理员手动录入已有中转站 Key，默认以 K-Sync 模式保存；数据库保存哈希、前后缀、加密后的上游 Key 和加密后的 SafetyHub Key，不在列表接口默认返回 Key 明文。启用 APIKey 后，`/v1/*` 请求会按客户端 Authorization 查询 `api_keys`，校验本地记录是否存在、active/revoked/expired 状态是否有效，并用解密后的上游 Key 替换转发到中转站的 Authorization。模型权限、token 额度、速率限制和资源能力权限由中转站负责，SafetyHub 不做模型/能力 allowlist 拦截，相关字段已从当前 schema、后台表单和 API 响应中删除。若数据库中还没有任何 APIKey，`/v1/*` 会保持阶段 1-4 的过渡透传行为，便于上线迁移。

阶段 6 已新增 `governance/key_provider.py`、`governance/providers/{passthrough,static_key,oneapi_nanfu_yxai}.py`，`main.py` lifespan 会根据 `KEY_PROVIDER_TYPE` 实例化 Provider 并注入 `ApiKeyService`。后台创建表单支持“手动录入中转站 Key”和“由 KeyProvider 创建”，Provider 创建默认 K-Sync，创建成功后返回完整 SafetyHub Key 供管理员复制；列表默认只展示前后缀，管理员可按需点击 reveal/复制完整 Key并写入操作审计。`oneapi_nanfu_yxai` 已对接 yxai 中转站登录、创建、获取完整 Key、删除和分页列表接口，支持 `KEY_PROVIDER_BASE_URL`、`KEY_PROVIDER_USERNAME`、`KEY_PROVIDER_PASSWORD_ENV`、`KEY_PROVIDER_AUTH_VERSION`、默认 quota 和重试参数配置。`scripts/import_yxai_keys.py` 已支持从 `yxai_token_export.json` 幂等导入历史中转站 Key；当前 PostgreSQL `api_keys` 表已有 23 条 active 记录，`upstream_key_encrypted` 与 `safetyhub_key_encrypted` 均存在。

当前代码尚未具备路径 C 自动续约迁移结果页、Provider 切换演练页、替换后首次请求失败自动回滚、图片资产后台预览/下载页面、图片资产存储配额和清理任务、告警通知、文件安全、审批运行链路和中转站配额/速率只读观测能力。

---

## 二、阶段完成情况

| 阶段 | 名称 | 当前状态 | 代码事实 |
|------|------|----------|----------|
| 阶段 1 | 透传中继 + 健康检查 | ✅ 已完成 | OpenAI-compatible `/v1/*` 通用透传、`/health/live`、`/health/ready`、Request ID、Header Policy、单上游路由已实现 |
| 阶段 2 | 弱扫描 MVP | ✅ 已完成 | Scanner、关键词/正则、block 伪装回复、desensitize 改写转发、弱规则集收敛、定时热加载、管理后台规则启停和手动热加载及对应测试已完成 |
| 阶段 3 | 归档 + 审计 | ✅ 已完成 | Chat 非流式/流式归档、block/desensitize 动作审计、文生图元数据归档、图片本体异步归档、图片资产状态 API、最近对话观测 API、SQLite 旧表缺列补齐、R1~R9 schema 预留和相关测试已完成 |
| 阶段 4 | 管理员认证 + 最小后台 | ✅ 已完成 | Basic Auth + IP 白名单、表单登录、后台静态页面鉴权、归档/审计/统计 API、规则管理 API、管理员操作审计和最小静态后台已完成 |
| 阶段 5 | APIKey 管理 | ✅ 已完成 | `middleware/identity.py`、`governance/api_keys.py`、K-Sync 创建、加密存储、APIKey 有效性校验、上游 Key 映射、后台 CRUD、单条替换和 CSV 批量替换上游 Key 已完成；模型/token/资源能力权限由中转站负责 |
| 阶段 6 | KeyProvider + 中转站联通 | ✅ 核心能力已完成 | 已实现 Provider 抽象、`passthrough/static/oneapi_nanfu_yxai`、后台 Provider 创建、reveal/复制完整 Key、Provider-aware 吊销、`.env` 配置和 JSON 导入 |
| 阶段 6A | 单实例 Docker 生产稳定性与高并发治理 | 🔄 当前生产上线范围 | 默认目标至少支持容器总 `1000` in-flight + `2000` 排队，支持 `.env` 或等价部署配置调整；流式与非流式统一进入 `/v1/*` 队列，不单独拆分并发池 |
| 阶段 7 | 扫描升级 | ⏸️ 暂不开发 | 当前仅保留规划记录，不进入近期开发；生产上线前不扩展完整 PII、分级策略和误报回归体系，继续使用阶段 2 已验证的低干扰规则集 |
| 阶段 8 | 可观测性 + 告警 | ⏸️ 暂不开发 | 当前仅保留规划记录，不进入近期开发；生产上线前不新增 Prometheus 指标、Webhook 告警、审计导出、图片资产后台预览/下载页面、存储配额和保留策略 |
| 阶段 9 | 审批 + 安全策略 + 审批链 | ⏸️ 暂不开发 | 当前仅保留规划记录，不进入近期开发；生产上线前不启用审批运行链路、策略绑定运行逻辑和审批链路由 |
| 阶段 10 | 远期能力 | ⏸️ 暂不开发 | 当前仅保留规划记录，不进入近期开发；生产上线前不启用文件解析、NER、配额、多上游和多租户能力 |

---

## 三、阶段 5 已实现能力明细

| 能力 | 文件 | 当前结果 |
|------|------|----------|
| APIKey 服务层 | `governance/api_keys.py` | 提供 K-Sync 创建、Key 哈希、前后缀提取、加密/解密、列表、详情、吊销、reveal、单条替换、批量替换和 Provider 创建能力 |
| 加密存储 | `governance/api_keys.py` | 使用 `SAFETYHUB_DATA_KEY` 派生密钥生成加密信封，数据库不保存上游 Key 和 SafetyHub Key 明文；开发环境未配置时使用本地开发派生 Key，生产环境要求配置数据密钥 |
| Identity 中间件 | `middleware/identity.py` | 解析 `/v1/*` Authorization，匹配 `api_keys` 记录，校验 active/expired/revoked 状态，并构建 request identity |
| 资源权限边界 | `middleware/identity.py`、`proxy/relay.py`、`storage/models.py` | SafetyHub 只校验 APIKey 本地记录有效性并替换上游 Key；模型权限、token 额度、速率限制和资源能力权限由中转站判定，相关字段已从 SafetyHub schema、后台表单和 API 响应中删除 |
| 上游 Key 替换 | `proxy/relay.py`、`proxy/header_policy.py` | 已启用 Header Policy 的 `upstream_api_key` 分支，转发时用解密后的上游 Key 替换客户端 SafetyHub Key |
| 归档与审计身份绑定 | `proxy/relay.py` | Chat 和文生图归档写入 `user_id`、`api_key_id`；命中审计写入 `user_id` |
| 后台 API | `admin/router.py`、`admin/schemas.py` | `/admin/api/api-keys` 支持手动创建、Provider 创建、列表、详情、reveal、吊销、单条替换和 CSV 批量替换 |
| 后台页面 | `admin/static/api_keys.html`、`admin/static/js/app.js`、`admin/static/css/style.css` | APIKey 页面支持手动录入/Provider 创建、列表查看、按需显示/复制完整 Key、吊销、单条替换和 CSV 批量替换，列表默认只展示前后缀 |
| 管理员操作审计 | `admin/router.py`、`storage/admin_ops.py` | 创建、查看详情、reveal、吊销、单条替换、批量替换均写入 `admin_operations` |
| SQLite 兼容 | `storage/database.py` | 对 `api_keys` 旧表补齐阶段 5/6 字段，包含 `safetyhub_key_encrypted`，避免已有 SQLite 数据库缺列导致写入失败 |
| 测试覆盖 | `tests/test_api_keys.py`、`tests/test_admin_stage4.py` | 覆盖 APIKey 服务、后台 CRUD、reveal、Provider 创建/吊销失败回滚、加密不回显、上游 Key 替换、allowlist 拒绝和阶段 4 兼容断言 |

---

## 四、阶段 5 边界与风险点

| 优先级 | 未完成项 | 影响 |
|--------|----------|------|
| P1 | 替换后首次请求验证新 upstream_key，失败时回滚旧 Key | 当前单条/批量替换会立即生效，但不自动触达上游验证新 Key 有效性；如新 Key 错误，需要管理员再次替换 |
| P1 | 标准加密库迁移 | 当前未新增第三方依赖，使用标准库加密信封满足不明文存储和完整性校验；后续如允许新增依赖，建议迁移到 Fernet 或 AES-GCM |
| P1 | Provider 自动续约迁移未实现 | 阶段 6 已支持 Provider 创建和同步吊销，但从旧中转站批量迁移到新 Provider 的路径 C、迁移进度页和失败重试仍待实现 |
| P1 | 图片资产后台预览/下载页面、存储配额和清理任务未实现 | 阶段 3 已保存图片本体与状态记录，但阶段 8 仍需补齐后台预览/下载、存储配额、保留策略和清理任务 |
| P1 | 告警通知未实现 | 高风险拦截不会推送企微/飞书 |

---

## 五、统一阶段口径

- 当前阶段统一为：**阶段 6A — 单实例 Docker 生产稳定性与高并发治理**。
- 阶段 1 至阶段 6 核心能力统一判定为：**已完成**；接下来只补齐阶段 6A 的上线前验证、配置安全、运维检查和高并发稳定性问题。
- 阶段 7 及之后统一判定为：**暂不开发**；相关内容仅作为长期规划保留，不进入当前生产上线范围，不作为上线阻塞项。
- 阶段 5 默认模式为 **K-Sync**：管理员录入的中转站 Key 同时作为客户端 SafetyHub Key 和上游 Key。
- 当管理员替换上游 Key 后，该记录自动进入 **K-Decoupled**：客户端 SafetyHub Key 不变，上游 Key 改为新中转站 Key。
- 阶段 5 的 APIKey 治理采用渐进启用策略：`api_keys` 表为空时保持历史透传；创建第一条 APIKey 后 `/v1/*` 开始执行 APIKey 有效性校验和上游 Key 映射，不接管中转站的模型/token/资源权限判断。
- 后续文档不再使用“旧阶段 0 / 旧阶段 1 第一批 / 第二批 / 第三批”表达，全部按新版 10 阶段路线图描述。

---

## 六、下一步开发计划

### 6.1 下一批次：阶段 6A 单实例生产稳定性与高并发治理

| 优先级 | 任务 | 目标产出 |
|--------|------|----------|
| P0 | `/v1/*` 全局有界并发队列 | 对所有 `/v1/*` 请求设置最大在途数、最大排队数和排队超时；默认目标至少为容器总 `1000` in-flight + `2000` 排队，支持通过 `.env` 或等价配置调整；超过容量返回兼容错误，管理端和健康检查不进入该队列 |
| P0 | 生产 Docker 启动方式收敛 | 去除 `--reload`；明确单实例 Docker 内 worker 数、总并发目标到每 worker 上限的折算规则、容器 CPU/内存/文件描述符要求 |
| P0 | 管理端保护 | `/admin/*` 和 `/health/*` 不受 `/v1/*` 压测队列影响；`/admin/api/stats` 增加短缓存；归档/审计列表保持分页和默认轻量查询 |
| P0 | 上游 HTTP 连接池复用 | 应用生命周期内复用上游 `AsyncClient`，配置最大连接数、keepalive、pool timeout、connect/read timeout，避免每请求创建 client |
| P1 | 审计归档削峰 | Chat 审计和归档从主请求链路中解耦为有界后台队列；队列满时可降级为元数据/采样/截断保存，保证主链路不被写库拖垮 |
| P1 | PostgreSQL 切库运行验证 | 当前 `.env` 已切换 PostgreSQL，APIKey 已完成迁移；继续补齐端口暴露、容器重启后连接稳定性、备份恢复和高并发写入保护验证 |
| P1 | 上线前全量验证 | 复跑编译检查、全量测试、APIKey/KeyProvider 专项测试、真实上游连通验证和高并发阶梯压测，确保阶段 1~6A 主链路稳定 |
| P1 | 生产配置安全复核 | 确认 `SAFETYHUB_DATA_KEY`、管理员密码、上游配置、Provider 凭据、IP 白名单、日志脱敏和高并发参数满足生产要求 |
| P2 | 非阻塞体验优化 | 仅处理不改变阶段范围的后台提示、文案、错误提示和操作说明优化 |

### 6.2 暂停开发范围

| 阶段 | 当前处理口径 |
|------|--------------|
| 阶段 7 | 暂不开发完整 PII 规则、20+ 关键词正式启用、分级策略、绕过防护和误报回归；生产上线继续沿用阶段 2 已验证的低干扰规则集 |
| 阶段 8 | 暂不开发 Prometheus 指标、Webhook 告警、告警限流、仪表盘增强、审计 CSV 导出、图片资产后台预览/下载、存储配额和保留策略 |
| 阶段 9 | 暂不开发临时审批、安全策略、审批链路由、多级审批和超时升级 |
| 阶段 10 | 暂不开发文件安全、NER、全文搜索、配额、多上游、多租户、SSO/角色权限 |

---

## 七、当前项目结构摘要

```text
NF-SafetyHub/
├── main.py
├── config.py
├── dependencies.py
├── engine/
├── proxy/
├── observability/
├── storage/
├── admin/
│   ├── router.py
│   ├── schemas.py
│   └── static/
│       ├── api_keys.html
│       ├── css/style.css
│       └── js/app.js
├── governance/
│   ├── __init__.py
│   ├── api_keys.py
│   ├── key_provider.py
│   └── providers/
│       ├── passthrough.py
│       ├── static_key.py
│       └── oneapi_nanfu_yxai.py
├── middleware/
│   ├── auth.py
│   └── identity.py
├── tests/
│   ├── test_admin_auth.py
│   ├── test_admin_stage4.py
│   ├── test_api_keys.py
│   ├── test_relay.py
│   └── ...
└── 产品研发控制/
```

---

## 八、验证结果

| 验证项 | 命令 | 当前结果 |
|--------|------|----------|
| APIKey / KeyProvider 专项测试 | `pytest tests/test_api_keys.py` | 通过，7 passed |
| 全量单元测试 | `pytest` | 通过，69 passed |
| APIKey 迁移验证 | `python scripts/verify_postgres_migration.py --tables api_keys` | SQLite 与 PostgreSQL 均为 23 条，`api_keys: sqlite=23 postgres=23 OK`；PostgreSQL 中 23 条记录均为 active，`upstream_key_encrypted` 与 `safetyhub_key_encrypted` 均存在 |
| 测试覆盖范围 | `tests/` | admin_auth、admin_stage4、api_keys、health、keyword、regex、scanner、fake_response、relay、header_policy、upstream_router、rules_config、rules_reload、archive、audit、models、observations |
| 代码结构检查 | 文件系统检查 | 阶段 5 APIKey 服务层、identity 中间件、后台接口、前端页面、SQLite 兼容已完成；阶段 6 Provider 抽象、`oneapi_nanfu_yxai`、reveal/复制、Provider-aware 吊销和导入脚本已补齐；迁移/验证脚本支持 SQLite 到 PostgreSQL 切换验证 |

---

## 九、当前注意事项

- 当前 `.env` 已配置 `KEY_PROVIDER_TYPE=oneapi_nanfu_yxai`、`KEY_PROVIDER_BASE_URL=https://yxai-api.nanfu.com`、`KEY_PROVIDER_USERNAME=800585` 和 `KEY_PROVIDER_AUTH_VERSION`；真实 `KEY_PROVIDER_PASSWORD` 只允许写入本地 `.env`，不得写入文档、测试代码、命令日志或 `.env.example`。
- 生产环境启用阶段 5/6 前应设置 `SAFETYHUB_DATA_KEY`，用于加密 `upstream_key_encrypted` 和 `safetyhub_key_encrypted`。
- 阶段 5/6 过渡策略为 `api_keys` 表为空时继续透传；创建或导入第一条 APIKey 后 `/v1/*` 开始要求客户端 Bearer Key 匹配有效记录。
- 后台列表和 API 列表响应默认只展示 Key 前后缀；管理员可通过受审计的 reveal 接口按需显示/复制完整 SafetyHub Key。
- Windows PowerShell 直接传中文 JSON 可能出现编码损坏，中文规则测试建议使用 UTF-8 请求体文件或 JSON Unicode 转义。
- 当前 block 拦截不会请求上游，但会写入归档和审计；阶段 8 告警暂不开发，不作为本次生产上线阻塞项。
- 当前 desensitize 只作用于 Chat Completions 请求侧 `messages` 文本字段；非 Chat 接口默认透明透传，响应内容原样透传。
- 当前运行环境已切换 PostgreSQL，SQLite 旧库保留为迁移来源和回退参考；当前仅按上线要求迁移 APIKey，其它历史归档/审计表未迁移。
- 当前 PostgreSQL 连接使用容器网络地址，容器重启后 IP 可能变化；后续应改为端口发布或统一 Compose 网络服务名，避免连接地址漂移。
- 当前数据库表通过 `create_all`、SQLite 缺列补齐和迁移脚本维持兼容，后续 schema 稳定后应评估引入 Alembic 或等效迁移机制。
