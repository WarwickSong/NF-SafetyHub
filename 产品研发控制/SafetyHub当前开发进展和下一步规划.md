# LLM-SafetyHub 当前开发进展和下一步规划

> 更新时间：2026-06-02  
> 当前阶段：阶段 3 — 归档 + 审计准备启动  
> 当前状态：阶段 1 OpenAI-compatible `/v1/*` 透传中继与健康检查已完成；阶段 2 弱扫描 MVP 已完成，具备 Scanner 调度、关键词/正则扫描、block 伪装回复、请求侧手机号 desensitize 改写转发、阶段 2 默认弱规则集收敛和规则定时热加载；阶段 3 归档 + 审计尚未开始。

---

## 一、实际代码状态

本状态基于当前仓库代码检查与测试结果。当前代码已经具备 FastAPI 应用入口、健康检查、Request ID、OpenAI-compatible `/v1/*` 通用中继转发、Header 安全透传、单上游路由、Scanner 调度、关键词/正则扫描、block 拦截伪装回复、请求侧手机号脱敏改写转发、基础 SSE 透传工具、规则定时热加载和静态后台首页骨架。

当前代码尚未具备消息归档写入、文生图元数据归档、文生图图片本体异步归档、审计写入、APIKey schema 预留、管理后台 API、管理后台认证、告警通知、文件安全、KeyProvider、审批链和配额能力。

---

## 二、阶段完成情况

| 阶段 | 名称 | 当前状态 | 代码事实 |
|------|------|----------|----------|
| 阶段 1 | 透传中继 + 健康检查 | ✅ 已完成 | OpenAI-compatible `/v1/*` 通用透传、`/health/live`、`/health/ready`、Request ID、Header Policy、单上游路由已实现；Chat Completions 进入请求侧扫描、脱敏和伪装拦截，非 Chat 接口默认透明透传 |
| 阶段 2 | 弱扫描 MVP | ✅ 已完成 | Scanner、关键词/正则、block 伪装回复、desensitize 改写转发、弱规则集收敛、定时热加载和对应测试已完成 |
| 阶段 3 | 归档 + 审计 | ⏳ 待开始 | 当前仅有基础 ORM 表；未实现 `storage/archive.py`、`storage/audit.py`、Chat 归档、文生图元数据归档、审计链路集成和 R1~R9 预留 |
| 阶段 4 | 管理员认证 + 最小后台 | ⏳ 待开始 | 仅有 `admin/static/index.html`、`style.css`、`app.js` 骨架；无 `admin/router.py`、`admin/schemas.py`、`middleware/auth.py` |
| 阶段 5 | APIKey 管理 | ⏳ 待开始 | 无 APIKey CRUD、identity 中间件、加密存储和上游 Key 替换能力 |
| 阶段 6 | KeyProvider + 中转站联通 | ⏳ 待开始 | `governance/` 仅有包初始化文件，无 Provider 抽象和适配器 |
| 阶段 7 | 扫描升级 | ⏳ 待开始 | 当前已有 20 条关键词 + 10 条正则配置，其中阶段 2 默认仅启用 5 条极保守关键词 block 和 2 条手机号 desensitize；扩展规则保留但默认关闭，尚未形成阶段 7 的 30+ PII、分级策略和误报回归体系 |
| 阶段 8 | 可观测性 + 告警 | ⏳ 待开始 | 无 Prometheus 指标、Webhook 告警、告警限流、审计导出、文生图图片本体异步归档、后台预览/下载、存储配额和保留策略 |
| 阶段 9 | 审批 + 安全策略 + 审批链 | ⏳ 待开始 | 无审批请求、策略表、审批链表和相关治理逻辑 |
| 阶段 10 | 远期能力 | ⏳ 待开始 | `file_security/` 仅有包初始化文件，无文件解析、NER、配额、多上游和多租户能力 |

---

## 三、已实现能力明细

### 3.1 阶段 1：透传中继 + 健康检查

| 能力 | 文件 | 当前结果 |
|------|------|----------|
| FastAPI 应用入口 | `main.py` | 生命周期中初始化数据库、Scanner、UpstreamRouter 和规则热加载任务，并注册 `/health`、`/v1` 路由 |
| 配置管理 | `config.py` | 使用 `pydantic-settings` 读取 `.env`，生产环境校验 `UPSTREAM_URL` 与 `ADMIN_PASSWORD` 强度 |
| 健康检查 | `observability/health.py` | 提供 `/health/live` 和 `/health/ready`，ready 检查数据库与规则文件 |
| Request ID | `observability/request_id.py` | 为请求生成或透传 `X-Request-ID` |
| Header Policy | `proxy/header_policy.py` | 剥离 Host、Hop-by-hop、Cookie、转发链路和内部 Header，保留 Authorization 等上游需要的 Header |
| 单上游路由 | `proxy/upstream_router.py` | 支持默认上游地址拼接 `/v1/*` 请求路径，预留 model/api_key/capability 参数 |
| 通用中继 | `proxy/relay.py` | 支持 OpenAI-compatible `/v1/*` 通用透传，保留查询参数并透传上游响应内容和状态码 |
| 安全治理入口 | `proxy/relay.py` | Chat Completions 提取 `messages` 并进入 Scanner；block 返回伪装回复，desensitize 改写请求侧文本后转发；Embeddings、Completions、Responses、Images、未知接口默认透明透传 |
| 流式透传工具 | `proxy/stream.py` | 支持 SSE 逐 chunk 透传和收集工具；当前 Chat stream 主链路使用逐 chunk 透传 |

### 3.2 阶段 2：弱扫描 MVP

| 能力 | 文件 | 当前结果 |
|------|------|----------|
| Scanner 数据模型 | `engine/models.py` | 定义 `ScannerResult`、`AggregatedScanResult`，支持 block/desensitize/warn/pass 判断 |
| Scanner 抽象基类 | `engine/base.py` | 定义 `scan`、`reload`、`name` 接口 |
| 文本归一化 | `engine/normalizer.py` | 支持 URL 解码、HTML unescape、NFKC、零宽字符移除、控制字符清理、空白压缩 |
| 扫描调度 | `engine/scanner.py` | 支持链式调度、block 早停、desensitize/warn 汇总、异常降级放行 |
| 关键词扫描 | `engine/rules_keyword.py` | 支持 enabled、contains/exact/prefix、大小写配置、命中片段脱敏和 reload |
| 正则扫描 | `engine/rules_regex.py` | 支持 enabled、预编译、ignore_case、错误规则跳过、命中片段脱敏和 reload |
| 规则配置 | `engine/rules_config.yaml` | 当前配置 20 条关键词规则、10 条正则规则；默认启用 5 条极保守关键词 block、`RG-PHONE-CN` 和 `RG-PHONE-INTL` desensitize，扩展规则默认关闭 |
| 伪装回复 | `proxy/fake_response.py` | block 请求返回 OpenAI Chat Completions 兼容 JSON 或 SSE 伪装回复 |
| 脱敏转发 | `proxy/relay.py` | 命中手机号 desensitize 后仅改写 Chat `messages` 文本字段，再转发上游；响应原样透传 |
| 规则热加载 | `main.py` | 应用启动后按 `rules_reload_interval` 周期调用 `scanner.reload_all()`，关闭时取消后台任务 |

### 3.3 测试与部署辅助

| 类别 | 当前结果 |
|------|----------|
| 单元/集成测试 | 当前共 34 个测试，覆盖 health、keyword、regex、scanner、fake_response、relay、header_policy、upstream_router、rules_config、rules_reload |
| 测试结果 | `.\.venv\Scripts\python.exe -m pytest` 实测通过，34 passed |
| 交付脚本 | 已存在 Windows/Linux 直接部署、Docker 部署、venv 初始化、engine/relay/venv 验证脚本 |
| 真实上游触达 | 文档记录本地上游为 `https://yxai-api.nanfu.com`，占位令牌请求可触达上游并返回 401/403 类认证响应 |

---

## 四、尚未完成与风险点

| 优先级 | 未完成项 | 影响 |
|--------|----------|------|
| P0 | 消息归档未实现 | 阶段 3 无法追溯 Chat prompt/response，后台查询无数据来源 |
| P1 | 文生图元数据归档未实现 | 阶段 3 无法沉淀文生图 prompt、参数和响应引用 |
| P1 | 文生图图片本体异步归档未实现 | 阶段 8 无法提供图片资产预览/下载、存储配额和保留策略 |
| P0 | 审计写入未实现 | block/warn/desensitize 命中事件不会进入 `audit_logs` |
| P0 | R1~R9 schema 预留未完成 | 阶段 5/6/9 后续启用 APIKey、策略、审批、配额时仍需改 schema |
| P1 | 管理后台认证和 API 未实现 | `admin/static/index.html` 只是静态骨架，不能查询归档和审计 |
| P1 | 告警通知未实现 | 高风险拦截不会推送企微/飞书 |
| P1 | 生产日志和审计脱敏链路未形成闭环 | 当前规则命中片段和请求侧手机号已做脱敏，后续归档/审计/告警路径尚未建立统一策略 |

---

## 五、统一阶段口径

### 5.1 阶段口径

- 当前阶段统一为：**阶段 3 — 归档 + 审计准备启动**。
- 阶段 1 统一判定为：**已完成**。
- 阶段 2 统一判定为：**已完成**。
- 阶段 3 统一判定为：**待开始**，直到归档、审计和 R1~R9 至少开始落地。
- 后续文档不再使用“旧阶段 0 / 旧阶段 1 第一批 / 第二批 / 第三批”表达，全部按新版 10 阶段路线图描述。

### 5.2 认证方案

- 阶段 4 管理后台认证统一采用 **Basic Auth + IP 白名单**。
- 当前 `config.py` 已有 `admin_username`、`admin_password`、`admin_ip_whitelist`，与 Basic Auth 方案兼容。
- 不采用 Bearer Token 登录态作为阶段 4 默认方案；如后续需要登录态或 SSO，放入阶段 10 或后续增强。

### 5.3 健康检查路径

- 健康检查统一为 `/health/live` 和 `/health/ready`。
- 不再使用 `/healthz`、`/readyz` 作为阶段 1 交付口径，除非代码后续显式增加兼容别名。

### 5.4 规则与脱敏策略

- 阶段 2 默认规则已收敛为弱扫描 MVP：手机号 desensitize + 5 条极保守关键词 block。
- 当前 `engine/rules_config.yaml` 中保留 20 条关键词 + 10 条正则作为阶段 7 扩展规则基础，但除阶段 2 默认规则外均默认关闭。
- 阶段 2 已补齐 desensitize 动作：命中手机号后替换 Chat `messages` 中对应文本，再转发脱敏后请求到上游，响应原样透传。
- 当前脱敏改写采用同一组手机号正则在 Chat 文本字段中递归替换，不直接使用合并扫描文本的 position 回写 JSON，避免多 message/content parts 偏移映射错误。

### 5.5 阶段 3 前置边界

阶段 3 可以启动。阶段 2 已满足阶段 3 最小进入条件：

- block 请求不发往上游并返回伪装回复。
- desensitize 请求改写 prompt 后发往上游。
- warn 请求放行；后续阶段 3 接入审计记录。
- pass 请求原样透传。
- 阶段 2 弱规则集默认启用，完整规则集保留但默认不扩大误报面。

---

## 六、下一步开发计划

### 6.1 当前批次：阶段 3 归档 + 审计

| 优先级 | 任务 | 目标产出 |
|--------|------|----------|
| P0 | 改造 `storage/models.py` | `MessageArchive` 增加 `prompt_original`、`prompt_desensitized`、`is_desensitized`；补齐 APIKey/策略/审批/配额预留表字段 |
| P0 | 实现 `storage/archive.py` | ArchiveWriter + ArchiveReader；支持正常、拦截、脱敏、流式请求归档 |
| P0 | 实现 `storage/audit.py` | AuditWriter + AuditReader；记录 pass/desensitize/warn/block 命中事件 |
| P0 | 集成 relay 归档 | Chat 非流式与流式路径均写入归档，失败不影响主链路 |
| P1 | 增加文生图元数据归档 | 记录 prompt、model、size、style、n、响应 URL 或 b64 存在状态、request_id、用户、时间；阶段 3 不保存图片本体 |
| P0 | 集成 scanner/relay 审计 | 所有命中事件写入 audit_logs，失败降级放行或继续返回当前响应 |
| P0 | 完成 R1~R9 预留 | Header 上游 Key 参数、ApiKeyRecord、SecurityPolicy、ApprovalChain、配额字段及相关测试 |
| P0 | 增加阶段 3 测试 | `tests/test_archive.py`、`tests/test_audit.py`、`tests/test_models.py`、Header 可选 upstream key 分支 |

### 6.2 后续批次概览

| 阶段 | 目标 |
|------|------|
| 阶段 4 | Basic Auth + IP 白名单、`admin/router.py`、`admin/schemas.py`、归档/审计/统计查询、最小静态后台 |
| 阶段 5 | APIKey 管理、K-Sync 默认、加密存储、单条/批量替换上游 Key、identity 中间件 |
| 阶段 6 | KeyProvider 抽象、passthrough/static/oneapi/openai_compat Provider、中转站联通创建和迁移 |
| 阶段 7 | 完整 PII 规则、20+ 关键词规则正式启用、分级策略、绕过防护、误报回归 |
| 阶段 8 | Prometheus 指标、Webhook 告警、告警限流、仪表盘增强、审计 CSV 导出、文生图图片本体异步归档、后台预览/下载、存储配额和保留策略 |
| 阶段 9 | 临时审批、安全策略、审批链路由、多级审批和超时升级 |
| 阶段 10 | 文件安全、NER、全文搜索、配额、多上游、多租户、SSO/角色权限 |

---

## 七、当前项目结构摘要

```text
NF-SafetyHub/
├── main.py
├── config.py
├── dependencies.py
├── engine/
│   ├── base.py
│   ├── models.py
│   ├── normalizer.py
│   ├── rules_config.yaml
│   ├── rules_keyword.py
│   ├── rules_regex.py
│   └── scanner.py
├── proxy/
│   ├── fake_response.py
│   ├── header_policy.py
│   ├── relay.py
│   ├── stream.py
│   └── upstream_router.py
├── observability/
│   ├── health.py
│   └── request_id.py
├── storage/
│   ├── database.py
│   ├── models.py
│   └── migrations/
├── admin/
│   └── static/
│       ├── index.html
│       ├── css/style.css
│       └── js/app.js
├── governance/
├── file_security/
├── notify/
├── middleware/
├── scripts/
│   └── init_db.py
├── tests/
│   ├── test_fake_response.py
│   ├── test_header_policy.py
│   ├── test_health.py
│   ├── test_keyword.py
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
└── 产品研发控制/
```

---

## 八、验证结果

| 验证项 | 命令 | 当前结果 |
|--------|------|----------|
| 全量单元测试 | `.\.venv\Scripts\python.exe -m pytest` | 通过，34 passed |
| 测试覆盖范围 | `tests/` | health、keyword、regex、scanner、fake_response、relay、header_policy、upstream_router、rules_config、rules_reload |
| 代码结构检查 | 文件系统检查 | 未发现阶段 3/4/5/6/8/9/10 关键实现文件 |
| IDE 诊断 | Trae/VS Code diagnostics | 无错误 |

---

## 九、当前注意事项

- 当前 `.env` 可配置真实 `UPSTREAM_URL`，但真实上游令牌不得写入文档、测试代码、命令日志或 `.env.example`。
- Windows PowerShell 直接传中文 JSON 可能出现编码损坏，中文规则测试建议使用 UTF-8 请求体文件或 JSON Unicode 转义。
- 当前 block 拦截不会请求上游，但也不会写入归档、审计或告警。
- 当前 desensitize 只作用于 Chat Completions 请求侧 `messages` 文本字段；非 Chat 接口默认透明透传，响应内容原样透传。
- 当前规则命中片段已做脱敏，后续归档、审计、告警和后台展示仍必须避免泄露 prompt 原文和 APIKey 明文。
- 当前数据库表通过 `create_all` 创建，阶段 3 schema 稳定后应评估引入 Alembic 或等效迁移机制。
- 当前 `admin/static/index.html` 只能视为前端骨架，不能代表阶段 4 管理后台完成。
