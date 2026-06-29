# LLM-SafetyHub 实现阶段规划

> 本文档将 SafetyHub 的全部功能映射到 10 个产品交付阶段。当前执行口径为：阶段 6A 之后优先新增阶段 6B 报表中心一期，用于交付日报、周报、月报和可下载 PDF/XLSX/CSV；阶段 7~10 内容仍作为长期规划保留，不作为当前报表一期阻塞项。

---

## 一、阶段总览

```
阶段 1   透传中继 + 健康检查
阶段 2   弱扫描 MVP（请求侧手机号脱敏 + 极保守关键词伪装回复 + 规则启停与热加载）
阶段 3   归档 + 审计
阶段 4   管理员认证 + 最小后台框架
阶段 5   APIKey 管理（K-Sync 默认 + 加密 + 上游 Key 替换）
阶段 6   KeyProvider 抽象 + 中转站联通创建
阶段 6A  单实例 Docker 生产稳定性与高并发治理
阶段 6B  报表中心一期（日报 + 周报 + 月报 + PDF/XLSX/CSV）
阶段 7   扫描升级（暂不开发，仅保留规划）
阶段 8   可观测性增强 + 告警（暂不开发，仅保留规划）
阶段 9   临时审批 + Key 级安全策略 + 审批链（暂不开发，仅保留规划）
阶段 10  远期能力（暂不开发，仅保留规划）
```

| 阶段 | 名称 | 对应版本 | 阶段目标 |
|------|------|---------|---------|
| 阶段 1 | 透传中继 + 健康检查 | v1.0 | 让客户端通过 SafetyHub 无感访问中转站，行为等价直连 |
| 阶段 2 | 弱扫描 MVP | v1.0 | 跑通 scanner + 脱敏 + 伪装回复链路，只启用低误报规则，并支持规则启停与热加载 |
| 阶段 3 | 归档 + 审计 | v1.0 | 保存原始 + 脱敏两份 prompt，记录所有命中事件，并完成 R1~R9 schema 预留 |
| 阶段 4 | 管理员认证 + 最小后台 | v1.0 | 管理后台可登录，可查询归档、审计、基础统计 |
| 阶段 5 | APIKey 管理 | v1.0 | 默认 K-Sync，支持加密存储、手动录入历史 Key、单条/批量替换上游 Key |
| 阶段 6 | KeyProvider + 中转站联通 | 已完成核心能力 | KeyProvider 抽象、中转站联通创建、reveal/复制、Provider-aware 吊销和历史 Key 导入核心能力已完成 |
| 阶段 6A | 单实例 Docker 生产稳定性与高并发治理 | 当前生产上线范围 | 不做水平扩展、不做按 Key 限流、不做上游熔断前提下，补齐 `/v1/*` 全局有界并发队列、生产启动方式、管理端保护、上游连接池复用、审计归档削峰、PostgreSQL 切库运行验证和压测验收 |
| 阶段 6B | 报表中心一期 | 当前新增规划 | 基于审计、请求、APIKey、Provider 和周期运行状态采样生成日报、周报、月报，支持 PDF/XLSX/CSV 下载、定时生成、手动覆盖重生、失败告警和 3 个月清理 |
| 阶段 7 | 扫描升级 | 暂不开发 | 仅保留规划；生产上线前不扩展完整 PII 检测、关键词扩充、分级决策和误报回归 |
| 阶段 8 | 可观测性 + 告警 | 暂不开发 | 仅保留规划；生产上线前不新增指标、仪表盘增强、Webhook 告警和审计导出 |
| 阶段 9 | 审批 + 策略 + 审批链 | 暂不开发 | 仅保留规划；生产上线前不启用临时审批、Key 级安全策略和多级审批链 |
| 阶段 10 | 远期能力 | 暂不开发 | 仅保留规划；生产上线前不启用文件安全、NER、配额、多上游和多租户等增强能力 |

---

## 二、阶段 1：透传中继 + 健康检查

**目标**：建立可运行的代理服务，支持 OpenAI 兼容 `/v1/*` 通用透传；阶段 1 重点保证所有符合 OpenAI 风格的接口可正常接收和转发，Chat Completions 作为主要安全治理入口进入扫描和伪装拦截，非 Chat 接口默认透明透传，后续仅按需增加脱敏或资产归档。

### 2.1 任务清单

| 任务 ID | 任务 | 所属模块 | 优先级 |
|---------|------|----------|--------|
| S1-01 | 创建项目目录结构与 `.gitignore` | 全局 | P0 |
| S1-02 | 编写 `config.py`，加载 `.env` 配置 | 全局 | P0 |
| S1-03 | 编写 `requirements.txt` | 全局 | P0 |
| S1-04 | 编写 `main.py` 与应用生命周期管理 | 全局 | P0 |
| S1-05 | 编写 `observability/health.py`，提供 `/health/live`、`/health/ready` 或等价健康检查 | 可观测性 | P0 |
| S1-06 | 编写 `observability/request_id.py`，生成或透传 Request ID | 可观测性 | P0 |
| S1-07 | 编写 `storage/database.py`，准备 SQLite/SQLAlchemy 基线 | 存储 | P0 |
| S1-08 | 编写 `proxy/stream.py`，支持 SSE 流式透传 | F1 | P0 |
| S1-09 | 编写 `proxy/header_policy.py`，处理 Header 透传、剥离与保留策略 | F14 | P0 |
| S1-10 | 编写 `proxy/upstream_router.py`，实现单上游路由并预留多上游接口 | F15 | P0 |
| S1-11 | 编写 `proxy/relay.py`，实现 OpenAI-compatible `/v1/*` 通用中继；Chat Completions 做请求侧扫描与伪装拦截，Embeddings/Completions/Responses/Images/未知接口默认透明透传，GET/DELETE 等无请求体接口透明透传 | F1 | P0 |
| S1-12 | 编写 `middleware/error_handler.py` 与基础异常处理 | 横切 | P1 |
| S1-13 | 编写 `middleware/request_limit.py`，限制请求大小与并发 | F14 | P1 |
| S1-14 | 编写 Dockerfile、docker-compose、Nginx 配置 | 部署 | P1 |
| S1-15 | 编写 CI、Makefile、初始化脚本 | 工程化 | P1 |
| S1-16 | 建立数据库迁移版本机制，后续变更不依赖 `create_all` 覆盖 | 存储 | P1 |

### 2.2 产出物

| 产出物 | 验收标准 |
|--------|---------|
| 本地可启动服务 | `docker compose up` 或本地 Python 启动后健康检查返回 200 |
| OpenAI 兼容中继 | `/v1/*` 通用透传；`POST /v1/chat/completions` 支持流式和非流式并进入扫描/伪装拦截；`POST /v1/embeddings`、`POST /v1/completions`、`POST /v1/responses`、`POST /v1/images/*`、未知接口和 `GET /v1/models` 等默认透明透传 |
| Header Policy | Authorization、Content-Type、Accept、X-Request-ID 等 Header 行为明确 |
| 单上游路由 | 当前只连一个中转站，但接口可替换为多上游实现 |
| Request ID | 所有请求自动生成或透传 `X-Request-ID` |
| 运行基线 | 健康检查、结构化日志、基础错误处理就绪 |
| 配置安全 | 生产必要配置缺失或弱密码时启动失败 |

### 2.3 验收标准

- [ ] `POST /v1/chat/completions` 正常非流式请求通过 SafetyHub 转发到中转站并获得正常回复
- [ ] `POST /v1/chat/completions` 正常流式请求逐 chunk 透传，无明显缓冲延迟
- [ ] `POST /v1/embeddings`、`POST /v1/completions`、`POST /v1/responses`、`POST /v1/images/*` 等非 Chat 接口可透明透传，不因敏感词命中而拦截
- [ ] `GET /v1/models` 等无请求体接口可透明透传并保留查询参数
- [ ] 未显式适配的 `/v1/*` 请求默认透明透传；后续仅在明确需要时对非 Chat 文本接口增加脱敏，不做伪装拦截
- [ ] SafetyHub 中继额外延迟 < 50ms
- [ ] 上游断开时错误能被清晰透传或转换为兼容错误响应
- [ ] 健康检查端点可被监控系统探测
- [ ] Request ID 能贯穿日志和响应 Header

---

## 三、阶段 2：弱扫描 MVP

**目标**：跑通完整安全链路，但只启用低误报规则。阶段 2 只做请求侧脱敏，不做响应脱敏。

### 3.1 扫描策略

| 类型 | 阶段 2 行为 | 阶段 7 升级方向 |
|------|------------|----------------|
| 手机号 | 请求侧仅对 `user`、`tool`、`function` 的 Chat messages 识别并脱敏后转发；跳过 `assistant`、`system`、`developer` | 扩展到更多 PII 类型 |
| 关键词 | 仅启用 3-5 个极保守关键词；Chat block 默认只扫描最新一条允许扫描 role 的有文本 message 并触发伪装回复；跳过 `assistant`、`system`、`developer` | 扩展到 20+ 条并接入分级策略 |
| 响应内容 | 原样透传，不脱敏 | 继续不做响应脱敏 |

**请求侧处理路径**

```text
客户端 prompt/messages → SafetyHub 扫描最新允许 role 的有文本 message 判断 block → 未拦截时仅脱敏 user/tool/function messages → 转发中转站 → 中转站响应原样返回客户端
```

**Chat role 处理边界**

- block 判定只看最新一条允许扫描 role 的有文本 message；允许 role 为 `user`、`tool`、`function`，用于覆盖普通用户输入和 Agent tool/function/file content 等尾部新增内容。
- `assistant`、`system`、`developer` 不参与 block 判定，避免前哨站过度干扰模型历史回复和提示词编排。
- 脱敏改写仅覆盖 `user`、`tool`、`function` messages，避免历史手机号等 PII 随这些输入来源重复外发。
- `assistant`、`system`、`developer` 不做脱敏改写，避免改写有效业务回复、系统提示词和开发者提示词。
- 调研依据：OpenAI-compatible Chat Completions 将工具执行结果作为 `role: "tool"` 消息回传；Claude Messages 将 `tool_result` 放在 `user` 消息中回传；Codex/Claude Code/Trae Agent 等编码 Agent 通常把本地工具执行结果追加回下一次模型请求。因此阶段 2 以 `user`、`tool`、`function` 作为允许扫描/脱敏 role，既覆盖主要 Agent 输入来源，又避免干扰 `assistant`、`system`、`developer`。
- 边界：OpenAI Responses API、Gemini Interactions/API 等非 Chat Completions 协议可能使用 `function_call_output`、`functionResponse`、`input` item 等结构，阶段 2 暂不套用 Chat role 规则，后续扩展时单独定义提取与脱敏策略。

**不做响应脱敏的原因**

- SafetyHub 的立意是防止企业内部敏感信息外流到外部模型供应商，风险方向是请求侧外发
- RAG、联网检索、客户支持等场景可能正常返回公开电话或地址，响应脱敏会破坏业务结果
- 请求侧已经脱敏后，中转站和模型不会收到原始敏感输入

### 3.2 任务清单

| 任务 ID | 任务 | 所属功能 | 优先级 |
|---------|------|----------|--------|
| S2-01 | 编写 `engine/models.py`（ScannerResult 等） | F6 | P0 |
| S2-02 | 编写 `engine/base.py`（Scanner 抽象基类） | F6 | P0 |
| S2-03 | 编写 `engine/normalizer.py`（Unicode、编码、零宽字符归一化） | F14 | P0 |
| S2-04 | 编写 `engine/scanner.py`（调度引擎） | F6 | P0 |
| S2-05 | 编写 `engine/rules_regex.py`，阶段 2 启用手机号脱敏规则 | F5 | P0 |
| S2-06 | 编写 `engine/rules_keyword.py`，阶段 2 启用极保守关键词 | F4 | P0 |
| S2-07 | 编写 `engine/rules_config.yaml`，配置弱扫描规则集 | F4/F5 | P0 |
| S2-08 | 编写 `proxy/fake_response.py`，返回 OpenAI 兼容伪装回复 | F2 | P0 |
| S2-09 | 在 `proxy/relay.py` 集成 scanner、脱敏、block 拦截与伪装回复 | F1/F2/F6 | P0 |
| S2-10 | 编写 `tests/test_keyword.py`、`tests/test_regex.py`、`tests/test_scanner.py` | 测试 | P0 |
| S2-11 | 编写 `tests/test_fake_response.py`、`tests/test_relay.py` | 测试 | P0 |
| S2-12 | ✅ 接入规则定时热加载，按 `rules_reload_interval` 周期调用 `reload_all()` | F4/F5 | P1 |
| S2-13 | ✅ 在管理后台提供规则启停 API 与页面操作，修改 `enabled` 后立即触发 `reload_all()` | F4/F5/F8 | P1 |
| S2-14 | ✅ 在管理后台提供手动规则热加载 API 与页面按钮，不修改配置，仅立即重载当前规则文件 | F4/F5/F8 | P1 |

### 3.3 阶段 2 默认规则集

| 规则类型 | 规则 ID | 行为 | 说明 |
|---------|---------|------|------|
| 正则 | RG-PHONE-CN | desensitize | 中国大陆手机号脱敏 |
| 正则 | RG-PHONE-INTL | desensitize | 国际电话格式脱敏 |
| 关键词 | KW-CONFIDENTIAL-1 | block | “告诉你一个公司机密” |
| 关键词 | KW-CONFIDENTIAL-2 | block | “保密协议内容” |
| 关键词 | KW-CONFIDENTIAL-3 | block | “这是绝密文件” |
| 关键词 | KW-CONFIDENTIAL-4 | block | “请记住以下密钥” |
| 关键词 | KW-CONFIDENTIAL-5 | block | “不要告诉别人” |

### 3.4 产出物

| 产出物 | 验收标准 |
|--------|---------|
| 扫描调度引擎 | 多个 Scanner 可链式调度，异常时降级放行并记录错误 |
| 手机号脱敏 | 请求中的手机号被替换后再发往中转站 |
| 保守关键词拦截 | 仅极少数测试关键词触发 block |
| 伪装回复 | block 请求不发往上游，返回符合 OpenAI 格式的 assistant 文本 |
| 兼容性保护 | function call / tools / reasoning 请求被拦截时不触发工具调用、不输出思考过程 |

### 3.5 验收标准

- [x] 手机号在请求侧被脱敏后才转发到中转站
- [x] 保守关键词命中后返回伪装回复，不发往中转站
- [x] 普通对话零误报
- [x] 响应原样透传，不做脱敏
- [x] ReDoS 攻击文本不导致服务卡顿
- [x] 全部单元测试通过

---

## 四、阶段 3：早期归档 + 审计

**历史目标**：建立数据追溯基础。Chat Completions 请求与响应进入消息归档，文生图请求同步写入元数据并异步归档图片本体，所有命中事件进入审计，同时完成 APIKey、配额、策略、审批链的 schema 预留。

> 当前阶段 6A 已调整：为降低长期空间占用，`message_archives` 完整归档写入已弃用；passed Chat 写入 `training_conversations`，desensitize/warn/block 写入 `audit_logs`，文生图图片资产写入 `image_assets`。

### 4.1 任务清单

| 任务 ID | 任务 | 所属功能 | 优先级 |
|---------|------|----------|--------|
| S3-01 | ✅ 编写 `storage/models.py`，当前保留 TrainingConversation、AuditLog、ApiKeyRecord、ApprovalRequest、SecurityPolicy、ApprovalChain 等当前运行模型，并统一 timezone-aware UTC 时间字段 | 存储 | P0 |
| S3-02 | ✅ 训练样本改由 `TrainingConversation` 存储 messages、assistant_response、trajectory、trajectory_hash 和治理字段；旧 `MessageArchive` 完整归档模型已移除 | F3/F6.1 | P0 |
| S3-03 | ✅ `storage/archive.py` 已收敛为 `ArchivePayload` 数据载体；旧 ArchiveWriter / ArchiveReader 已移除 | F3 | P0 |
| S3-04 | ✅ 非流式路径集成归档 | F3 | P0 |
| S3-05 | ✅ 流式路径收集完整 SSE 响应后归档，包含原始 SSE 内容和提取后的 `message_content` | F3 | P0 |
| S3-06 | ✅ 增加文生图元数据归档：prompt、model、size、style、n、response URL 或 b64 存在状态、request_id、时间，并记录资产数量、来源和调度状态 | F3 | P1 |
| S3-12 | ✅ 实现文生图图片本体异步归档：支持 b64_json 解码、URL 下载、sha256 命名、大小限制、mime_type 检测、状态记录和失败降级 | F3/F14 | P1 |
| S3-13 | ✅ 增加 `/admin/api/image-assets` 图片资产状态查询接口，沿用后台鉴权和管理员操作审计，不直接暴露图片静态目录 | F3/F8/F14 | P1 |
| S3-07 | ✅ 编写 `storage/audit.py`（AuditWriter） | F7 | P0 |
| S3-08 | 🟡 在 scanner/relay 中写入 desensitize/block 命中审计；warn 规则当前默认未启用，pass 无命中不写审计 | F7 | P0 |
| S3-09 | ✅ 写入失败降级，归档或审计失败不得影响主链路 | F3/F7 | P0 |
| S3-10 | ✅ 编写 `tests/test_audit.py`、`tests/test_observations.py`、`tests/test_models.py`、`tests/test_training.py`、Header 可选 upstream key 分支和 relay 流式/文生图归档测试 | 测试 | P0 |
| S3-11 | ✅ 增加 `/admin/api/observations/recent` 最近对话观测 API，用于上线初期查看真实 role/messages 样本 | F3/F8 | P0 |

### 4.2 R1~R9 预留任务

| 任务 ID | 改动 | 文件 | 兼容性保证 |
|---------|------|------|-----------|
| S3-R1 | ✅ `build_upstream_headers` 增加 `upstream_api_key=None` 可选参数 | `proxy/header_policy.py` + `proxy/relay.py` | 当前传 `None`，透传行为不变 |
| S3-R2 | ✅ 新增 `ApiKeyRecord`，含 `provider_name`、`upstream_key_id`、`upstream_key_encrypted`、`is_decoupled` 等字段 | `storage/models.py` | 表存在但无人写入 |
| S3-R3 | ✅ 新增 `key_provider_type="passthrough"` 与 `key_provider_admin_token=""` | `config.py` | 默认不启用 Provider |
| S3-R4 | ✅ 测试 `upstream_api_key=None` / `="sk-real"` 两条 Header 分支 | `tests/test_header_policy.py` | 防止透传退化 |
| S3-R5 | ✅ 测试 `api_keys` 表创建与字段齐全 | `tests/test_models.py` | schema 预留可验证 |
| S3-R6 | ✅ 明确不在 `ApiKeyRecord` 预留模型配额、能力配额、速率限制和用量快照字段 | `storage/models.py` | 资源权限与配额由中转站管理，SafetyHub schema 保持干净 |
| S3-R7 | ✅ 补齐 `security_policy_id`、`approval_chain_id`、`cost_center`、`chain_id`、`current_level`、`escalated_at` 等关联字段 | `storage/models.py` | 全部 NULL 默认 |
| S3-R8 | ✅ 新增 `SecurityPolicy` 与 `ApprovalChain` 两张表 | `storage/models.py` | 表存在但无人写入 |
| S3-R9 | ✅ 测试 6 张表 `create_all` 能成功，预留字段默认值正确 | `tests/test_models.py` | 防止后续迁移遗漏 |

### 4.3 产出物

| 产出物 | 验收标准 |
|--------|---------|
| 训练样本（阶段 6A 当前口径） | passed Chat 写入 `training_conversations`，包含 request_id、model、capability、messages、assistant_response、trajectory、trajectory_hash、user_id/api_key_id、脱敏状态和治理字段 |
| 最近观测 API | 当前 `/admin/api/observations/recent` 读取最近少量训练样本，用于上线初期查看 role/messages/assistant response 结构 |
| 文生图图片资产归档 | 文生图响应中的 URL / b64_json 图片本体异步保存，记录 request_id、local_path、sha256、mime_type、size_bytes、status 和 error；不再写入 `message_archives` 图片 metadata |
| 审计日志 | 已对命中事件独立记录规则 ID、级别、命中片段、全文 hash、时间；pass 无命中暂不写入审计 |
| 预留 schema | APIKey、审批、策略、配额相关字段与表均存在 |
| 降级策略 | 数据库异常不影响用户请求 |

### 4.4 验收标准

- [x] Chat passed 请求能写入 `training_conversations`
- [x] 训练样本/审计/图片资产失败不影响主链路
- [x] 最近对话观测 API 能返回 role、messages、assistant response 和脱敏状态
- [x] Chat 流式请求能提取 assistant response 并形成训练样本
- [x] 文生图请求能异步保存 b64_json / URL 图片本体与状态到 `image_assets`
- [x] 命中事件写入 audit_logs，包含 block/desensitize；warn 规则启用后沿用同一审计写入链路
- [x] `message_archives` 完整归档写入已弃用，运行后不应增长
- [x] APIKey 管理预留完成，当前透传行为零变化
- [x] 6 张表创建成功，所有预留字段齐全

---

## 五、阶段 4：管理员认证 + 最小后台框架

**目标**：后台可登录、可查询、可审计，为阶段 5 的 APIKey 管理提供安全入口。

### 5.1 任务清单

| 任务 ID | 任务 | 所属功能 | 优先级 |
|---------|------|----------|--------|
| S4-01 | ✅ 编写 `middleware/auth.py`，保护 `/admin/*` | F8 | P0 |
| S4-02 | ✅ 编写 `admin/schemas.py` | F8 | P0 |
| S4-03 | ✅ 编写 `admin/router.py`，提供训练样本、审计、统计 API | F8 | P0 |
| S4-04 | ✅ 编写 `storage/admin_ops.py`，记录管理员操作审计 | F14 | P0 |
| S4-05 | ✅ 编写 `admin/static/index.html` 仪表盘 | F8 | P0 |
| S4-06 | ✅ 编写 `admin/static/archives.html` 训练样本页 | F8 | P0 |
| S4-07 | ✅ 编写 `admin/static/blocks.html` 拦截/审计页 | F8 | P0 |
| S4-08 | ✅ 编写 `admin/static/rules.html` 规则管理页，承载阶段 2 已完成的启停和热加载操作 | F8/F4/F5 | P1 |
| S4-09 | ✅ 编写 `admin/static/api_keys.html` APIKey 页面；阶段 5 已升级为可操作页面 | F15 | P1 |
| S4-10 | ✅ 编写 `admin/static/approvals.html` 审批只读占位页 | F16 | P1 |
| S4-11 | ✅ 编写 `admin/static/settings.html` 系统设置页 | F8/F14 | P1 |
| S4-12 | ✅ 编写 `admin/static/css/style.css` 与 `admin/static/js/app.js` | F8 | P1 |

### 5.2 产出物

| 产出物 | 验收标准 |
|--------|---------|
| 管理后台认证 | 未登录访问 `/admin/*` 返回 401 |
| 后台 API | 训练样本查询、审计查询、统计概览全部可用 |
| 后台前端 | 仪表盘、拦截记录、训练样本、规则、设置可访问 |
| 预留页面 | APIKey/模型权限、审批记录页面有入口与只读占位 |
| 管理员操作审计 | 查看详情、导出、规则变更、审批动作都有操作日志 |

### 5.3 验收标准

- [x] 管理员可以登录后台
- [x] 未登录无法访问后台 API 和页面
- [x] 后台可按时段、用户、关键词筛选训练样本和审计
- [x] 统计面板展示今日请求数、命中数、拦截数、趋势
- [x] 管理员操作写入 admin_operation_logs

---

## 六、阶段 5：APIKey 管理（K-Sync 默认 + 加密 + 替换能力）

**目标**：启用 SafetyHub 自身 APIKey 管理。默认让前哨站 Key 与中转站 Key 一致，保留随机生成能力但默认不开启，并支持后续替换中转站 Key 时保持客户端 Key 不变。

### 6.1 K-Sync / K-Decoupled 设计

| 模式 | 客户端 Key | 上游 Key | 默认 | 说明 |
|------|-----------|---------|------|------|
| K-Sync | 中转站 Key | 同一个中转站 Key | 是 | 阶段 5 默认，便于丢失后从中转站或客户端配置找回 |
| K-Decoupled | `sk-sh-xxx` | 独立中转站 Key | 否 | 替换上游 Key 后自动进入，客户端无感 |

### 6.2 任务清单

| 任务 ID | 任务 | 所属功能 | 优先级 |
|---------|------|----------|--------|
| S5-01 | ✅ 编写 `middleware/identity.py`，解析 Authorization 并查询 `api_keys` | F15 | P0 |
| S5-02 | ✅ 实现 `governance/api_keys.py`，提供 CRUD、哈希、加密存储 | F15 | P0 |
| S5-03 | ✅ K-Sync 新建逻辑：`safetyhub_key == upstream_key`，`is_decoupled=False` | F15.1.5 | P0 |
| S5-04 | ✅ 使用 `SAFETYHUB_DATA_KEY` 加密 `upstream_key_encrypted`；当前未新增第三方依赖，使用标准库加密信封并保留后续迁移 Fernet/AES-GCM 空间 | F15 | P0 |
| S5-05 | ✅ 明确资源权限边界并删除超边界字段：SafetyHub 不执行模型 allowlist、token 额度或 capability allowlist，模型/token/资源能力权限由中转站作为权威系统管理；`model_allowlist`、`capability_allowlist`、配额和速率限制字段不进入 SafetyHub 当前 schema | F15 | P0 |
| S5-06 | ✅ 后台 `/admin/api/api-keys` CRUD 接口 | F15 | P0 |
| S5-07 | ✅ `admin/static/api_keys.html` 编辑能力：创建、列表、吊销、绑定中转站 Key | F15 | P0 |
| S5-08 | ✅ 路径 A：单条替换上游 Key | F15.1.6 | P0 |
| S5-09 | ✅ 路径 B：CSV 批量替换上游 Key | F15.1.6 | P0 |
| S5-10 | ✅ 替换后自动标记 `is_decoupled=True`，客户端 Key 不变 | F15.1.5 | P0 |
| S5-11 | ✅ 替换操作写入 admin_operation_logs | F14/F15 | P0 |
| S5-12 | ⏳ 替换后首次请求验证新 upstream_key，失败时回滚旧 Key | F15 | P1 |

### 6.3 产出物

| 产出物 | 验收标准 |
|--------|---------|
| APIKey 管理 | 管理员可创建、查看、吊销、导入 Key |
| K-Sync 默认 | 新建 Key 默认前哨站 Key = 中转站 Key |
| 加密存储 | 数据库不存明文 Key，列表只展示前后缀 |
| 单条替换 | 单个 Key 可替换上游 Key，客户端无感 |
| 批量替换 | CSV 可批量导入新中转站 Key 顶替旧中转站 Key |
| 资源权限边界 | SafetyHub 不判定模型、token 额度和资源能力权限，这些权限由中转站判定；SafetyHub 仅保存上游 Key 映射并执行安全治理，超边界字段不进入当前 schema |

### 6.4 验收标准

- [x] 历史中转站 Key 可手动录入 SafetyHub 并立即使用
- [x] 新建 Key 默认 K-Sync，丢失时可从中转站找回并重录
- [x] 单条替换上游 Key 后客户端 Authorization 不变
- [x] CSV 批量替换支持成功/失败结果汇总
- [x] Key 明文不进入日志、告警、数据库明文字段或后台列表
- [x] 模型权限、token 额度、速率限制和资源能力权限不由 SafetyHub 默认接管，统一交由中转站作为权威系统判定

---

## 七、阶段 6：KeyProvider 抽象 + 中转站联通创建

**目标**：把 APIKey 创建、吊销、查询从 SafetyHub 内部抽象为 Provider，实现可视化联通中转站创建不同权限的 Key。

### 7.1 任务清单

| 任务 ID | 任务 | 所属功能 | 优先级 |
|---------|------|----------|--------|
| S6-01 | ✅ 实现 `governance/key_provider.py` 抽象基类、UpstreamKeyInfo、KeyCreateParams、工厂方法 | F15.2 | P0 |
| S6-02 | ✅ 实现 `governance/providers/passthrough.py` | F15.2 | P0 |
| S6-03 | ✅ 实现 `governance/providers/static_key.py` | F15.2 | P0 |
| S6-04 | ✅ 实现 `governance/providers/oneapi_nanfu_yxai.py`，对接 yxai 登录、创建、取完整 Key、删除和分页列表接口 | F15.2 | P0 |
| S6-05 | ⏳ 实现通用 `openai_compat.py` / 通用 OneAPI Provider | F15.2 | P1 |
| S6-06 | ✅ 在 `main.py` lifespan 中根据 `key_provider_type` 实例化 Provider | F15.2 | P0 |
| S6-07 | ✅ 后台一键调用中转站创建同名/同 owner Key，并获取中转站返回的 upstream_key；模型、token、能力权限在中转站侧配置和生效 | F15.2 | P0 |
| S6-08 | ⏳ Provider 切换演练（oneapi_nanfu_yxai ↔ static），验证核心链路零改动 | F15.2 | P1 |
| S6-09 | ⏳ 路径 C：通过新 Provider 自动续约迁移所有 Key | F15.1.6 | P1 |
| S6-10 | ✅ 批量导入支持脚本导入 `yxai_token_export.json`；当前 PostgreSQL `api_keys` 已迁移验证 23 条 active 记录，CSV/表单粘贴迁移增强待后续 | F15 | P1 |
| S6-11 | ✅ 完整 SafetyHub Key 按需 reveal/复制，写入管理员操作审计，列表默认只展示前后缀 | F15/F14 | P0 |
| S6-12 | ✅ Provider-aware 吊销：中转站删除成功后才标记本地 revoked，失败返回错误不假成功 | F15.2/F14 | P0 |

### 7.2 产出物

| 产出物 | 验收标准 |
|--------|---------|
| KeyProvider 抽象 | ✅ 新 Provider 不改 relay/scanner/archive/audit 核心链路 |
| yxai OneAPI/OneHub 适配 | ✅ `oneapi_nanfu_yxai` 可调用中转站接口创建、吊销、查询/列表 Key |
| 完整 Key reveal/复制 | ✅ 管理员按需 reveal/复制完整 SafetyHub Key，写入审计，列表默认不返回明文 |
| 历史 Key 导入与 PostgreSQL 迁移 | ✅ `scripts/import_yxai_keys.py` 可幂等导入 `yxai_token_export.json`；`scripts/verify_postgres_migration.py --tables api_keys` 验证 SQLite 与 PostgreSQL 均为 23 条 |
| OpenAI 兼容适配 | ⏳ 支持通用兼容协议供应商，待后续增强 |
| 自动续约迁移 | ⏳ 从旧中转站迁移到新中转站时客户端 Key 不变，待后续增强 |

### 7.3 验收标准

- [x] 后台可视化调用中转站创建同名/同 owner Key，并保存中转站返回的 upstream_key
- [x] Provider 创建失败时 SafetyHub 记录回滚；本地落库失败时尝试吊销已创建的上游 Key
- [x] Provider 查询失败不阻塞主链路；主链路只依赖本地加密映射
- [x] 吊销 Provider Key 时先删除中转站 Key，成功后才标记本地 revoked
- [x] 完整 SafetyHub Key 可通过受审计 reveal 接口按需展示/复制
- [ ] 自动续约迁移支持中断恢复和失败重试

---

## 八、阶段 6A：单实例 Docker 生产稳定性与高并发治理

**当前口径**：当前生产上线范围。短期按单实例 Docker 部署设计，不考虑水平扩展实例；`/v1/*` 采用全局有界并发队列保护主链路；结合 100 名员工同时使用 OpenClaw/Hermes/批量标注 Agent 的峰值生产场景，目标至少支持容器总 `1000` in-flight + `2000` 排队，并允许通过 `.env` 或等价部署配置调整；流式与非流式统一纳入 `/v1/*` 队列，不单独拆分并发池；暂不做按 Key 限流、上游熔断和多上游切换。

**目标**：让单实例在高并发压测下保持稳定、可排队、可观测、可恢复，并尽量保证管理端和健康检查可用；默认生产配置以 4 worker 场景为基准折算为每 worker `250` in-flight + `500` 排队。

### 8.1 任务清单

| 任务 ID | 任务 | 所属功能 | 优先级 |
|---------|------|----------|--------|
| S6A-01 | 新增 `/v1/*` 全局有界并发队列，配置最大在途请求数、最大排队数、排队超时和超限响应；默认目标至少支持容器总 `1000` in-flight + `2000` 排队 | F14/F1 | P0 |
| S6A-02 | 明确多 worker 折算规则：若单实例 Docker 内启用多个 worker，进程内并发上限按 worker 数折算为容器总上限；代码默认每 worker `V1_MAX_INFLIGHT=150`、`V1_MAX_QUEUE_SIZE=200`；4 worker 生产环境推荐通过 `.env` 调到每 worker `V1_MAX_INFLIGHT=250`、`V1_MAX_QUEUE_SIZE=500` 以达到容器总目标 1000 in-flight + 2000 排队 | F14/部署 | P0 |
| S6A-03 | 生产启动去除 `--reload`，Docker 启动脚本和文档统一使用生产模式 worker 参数 | 部署 | P0 |
| S6A-04 | 管理端保护：`/admin/*`、`/admin/api/*`、`/health/*` 不进入 `/v1/*` 并发队列，避免压测流量拖死后台 | F8/F14 | P0 |
| S6A-05 | `/admin/api/stats` 增加短缓存，归档/审计列表保持分页和默认轻量查询 | F8 | P0 |
| S6A-06 | 上游 HTTP 连接池复用：应用生命周期内维护共享 `httpx.AsyncClient`，配置最大连接、keepalive、pool timeout、connect/read timeout | F1/部署 | P0 |
| S6A-07 | 审计与归档削峰：将 Chat 审计、非流式归档和流式归档收尾写入改为有界后台队列，支持批量写入和队列满降级；流式不单独管理并发，但归档必须受截断和队列上限保护 | F3/F7/F14 | P1 |
| S6A-08 | 归档内容控制：限制 response/prompt 归档最大字节数，保存截断标记、原始大小、usage、latency 和命中规则摘要 | F3 | P1 |
| S6A-09 | PostgreSQL 切库运行验证：APIKey 迁移验证、连接地址稳定性、备份恢复、索引复核和高并发写入保护；SQLite 保留为兼容和回退参考 | 存储/部署 | P1 |
| S6A-10 | 日志降噪：压测期间不输出完整 prompt/response，access log 可关闭或采样，保留 request_id、状态、耗时和错误摘要 | F14/运维 | P1 |
| S6A-11 | 容器资源基线：明确 CPU、内存、文件描述符、连接数、Docker 日志滚动和健康检查参数 | 部署/运维 | P1 |
| S6A-12 | 高并发压测验收：增加阶梯压测、后台可用性、队列超时、队列满、上游慢响应和数据库高压场景验证 | 测试 | P0 |

### 8.2 推荐配置口径

| 配置 | 建议默认 | 说明 |
|------|----------|------|
| `V1_MAX_INFLIGHT` | 代码默认 150/worker；生产推荐 250/worker，4 worker 容器总目标 1000；可通过 `.env` 调整 | 每个进程内同时进入业务链路的 `/v1/*` 请求数 |
| `V1_MAX_QUEUE_SIZE` | 代码默认 200/worker；生产推荐 500/worker，4 worker 容器总目标 2000；可通过 `.env` 调整 | 每个进程内允许等待并发令牌的请求数 |
| `V1_QUEUE_TIMEOUT_SECONDS` | 默认 10~15；可通过 `.env` 调整 | 请求排队超过该时间后返回 429/503 |
| `UPSTREAM_MAX_CONNECTIONS` | 与 `V1_MAX_INFLIGHT` 同量级 | 避免上游连接池小于业务并发导致二次排队 |
| `UPSTREAM_MAX_KEEPALIVE_CONNECTIONS` | `UPSTREAM_MAX_CONNECTIONS` 的 30%~70% | 复用连接并控制空闲连接数量 |
| `ADMIN_STATS_CACHE_SECONDS` | 5~15 | 压测期间保护后台首页统计接口 |
| `ARCHIVE_QUEUE_MAX_SIZE` | 1000~5000 | 有界后台队列，避免内存无限增长 |
| `ARCHIVE_BATCH_SIZE` | 20~100 | 批量写库，减少 commit 次数 |

### 8.3 产出物

| 产出物 | 验收标准 |
|--------|---------|
| `/v1/*` 并发闸门 | 高并发下最大在途数不超过配置值；默认 4 worker 下容器总目标至少为 `1000` in-flight + `2000` 排队；超限请求进入有界队列，排队超时或队列满时返回明确错误 |
| 管理端保护 | `/admin/*` 和 `/health/*` 不被 `/v1/*` 队列阻塞；压测期间后台登录、首页和规则页保持可访问 |
| 上游连接池 | 高并发请求复用共享连接池，不再每请求创建新的 HTTP client |
| 归档削峰 | 主请求链路不等待归档写库完成；归档队列满时按策略降级且不影响响应返回 |
| PostgreSQL 运行验证 | APIKey 已迁移到 PostgreSQL；继续验证连接地址稳定性、备份恢复、索引复核和高并发写入削峰 |
| 生产 Docker 运行方式 | 不使用 `--reload`，worker 数、并发参数和容器资源要求可配置 |
| 压测验收报告 | 记录 worker 数、并发参数、队列参数、数据库类型、上游类型、p95/p99、错误率和后台可用性 |

### 8.4 验收标准

- [ ] `python test_llm_throughput.py --mode ramp-up` 阶梯压测下，`/v1/*` 在途请求数受配置上限约束
- [x] 队列满或排队超时时返回 429/503，不出现请求无限挂起，已由 `tests/test_concurrency_limit.py` 覆盖
- [x] `/health/live`、`/health/ready` 不进入 `/v1/*` 队列；压测期间快速返回仍需实测记录
- [x] 管理员页面不进入 `/v1/*` 队列，`/admin/api/stats` 已支持短缓存；压测期间表现仍需实测记录
- [x] 非流式和流式 Chat 请求统一使用 `/v1/*` 并发闸门，不单独拆分流式并发池，并保持 OpenAI-compatible 响应格式
- [ ] 上游连接池配置可观测，连接数不随请求数无限增长
- [x] 归档/审计写入异常或队列满不影响主链路响应，已通过有界后台队列和降级 fallback 实现
- [x] Docker 生产启动不包含 `--reload`；容器重启后规则、数据库和 KeyProvider 初始化仍需生产环境验证

---

## 九、阶段 7：扫描升级

**当前口径**：暂不开发，仅保留规划记录；生产上线前继续使用阶段 2 已验证的低干扰规则集，不扩展完整 PII、关键词分级、绕过防护和误报回归体系。

**规划目标**：从弱扫描升级为完整扫描规则集，覆盖更多 PII 与敏感信息，支持命中分级和规则热加载。

### 8.1 任务清单

| 任务 ID | 任务 | 所属功能 | 优先级 |
|---------|------|----------|--------|
| S7-01 | 正则规则扩展到 30+ 条 | F5 | P0 |
| S7-02 | 覆盖姓名、地址、身份证、信用卡、银行卡、邮箱、IP、URL、API Key 等 | F5 | P0 |
| S7-03 | 关键词规则扩展到 20+ 条 | F4 | P0 |
| S7-04 | 分级决策策略配置：pass / desensitize / warn / block | F6 | P0 |
| S7-05 | 白名单规则配置 | F4/F5 | P0 |
| S7-06 | 完整规则集启用后的误报回归与启停回归验证，沿用阶段 2 已完成的热加载机制 | F4/F5 | P0 |
| S7-07 | 绕过路径安全测试：URL 编码、分段发送、Unicode 混淆 | F14 | P0 |
| S7-08 | DLP 规则回归测试：正常文本 100 条 → 0 误报 | 测试 | P0 |
| S7-09 | ReDoS 防护：匹配超时与降级策略 | F5 | P0 |
| S7-10 | 编写规则配置说明 | F4/F5 | P1 |

### 8.2 产出物

| 产出物 | 验收标准 |
|--------|---------|
| 完整正则规则库 | 30+ 条规则，覆盖主要 PII 类型 |
| 完整关键词规则库 | 20+ 条规则，覆盖商业机密、技术机密、人事机密、客户名单、财务数据 |
| 分级决策 | 不同规则可触发 pass/desensitize/warn/block |
| 规则启停回归 | 完整规则集扩容后，阶段 2 已完成的启停和热加载机制仍可稳定生效 |
| 绕过防护 | URL 编码、分段、Unicode 混淆等路径被覆盖 |

### 8.3 验收标准

- [ ] 普通对话误报率 < 0.1%
- [ ] 20 条敏感测试文本全部命中预期规则
- [ ] 安全检测耗时 < 10ms/请求
- [ ] 规则被绕过风险有专门测试覆盖

---

## 十、阶段 6B：报表中心一期

**权威规划**：详见 `SafetyHub报表中心一期规划.md`。阶段 6B 将原阶段 8 中“审计 CSV 导出”的部分能力提前并升级为完整报表中心，同时纳入运行状态周期采样；Prometheus 指标和通用告警平台仍保留在阶段 8 长期规划。

### 10.1 任务清单

| 任务 ID | 任务 | 所属功能 | 优先级 |
|---------|------|----------|--------|
| S6B-01 | 新增报表元数据表和覆盖重生唯一约束 | F21 | P0 |
| S6B-02 | 实现日报、周报、月报周期计算，统一 `Asia/Shanghai` | F21 | P0 |
| S6B-03 | 实现审计、总请求、APIKey、Provider 和运行状态采样聚合服务 | F21 | P0 |
| S6B-04 | 生成 CSV 明细和 XLSX 多 Sheet 报表 | F21 | P0 |
| S6B-05 | 测试 WeasyPrint 与 ReportLab 两种 PDF 方案并确定正式实现 | F21 | P0 |
| S6B-06 | 实现 PDF 报表模板和文件 hash | F21 | P0 |
| S6B-07 | 实现定时任务：日报 02:00、周报 03:00、月报 04:00 | F21 | P0 |
| S6B-08 | 实现手动覆盖重生和敏感字段可选导出 | F21/F14 | P0 |
| S6B-09 | 实现报表列表、详情、下载和失败重试 API | F21/F8 | P0 |
| S6B-10 | 新增报表中心前端页面 | F21/F8 | P0 |
| S6B-11 | 新增运行状态采样表和采样定时任务，默认 5 分钟采样一次 | F21/F12 | P0 |
| S6B-12 | 复用 `/app/data/reports` 挂载并补充 Docker、离线部署和备份说明 | 运维/F20 | P0 |
| S6B-13 | 实现失败 Webhook 告警、任务锁和 3 个月文件/元数据/采样数据清理 | F21/F9 | P1 |

### 10.2 产出物

| 产出物 | 验收标准 |
|--------|---------|
| 报表中心页面 | 管理员可查询日报、周报、月报状态并下载 PDF/XLSX/CSV |
| 定时报表 | 系统按 02:00、03:00、04:00 错峰生成上一周期报表 |
| 手动重生 | 管理员可覆盖重生指定周期，并选择是否包含敏感字段 |
| 文件归档 | 文件保存到 `/app/data/reports`，元数据和文件均保留 3 个月 |
| 运行状态采样 | 周期采集 CPU、内存、磁盘、并发队列、归档队列和健康状态，并在 PDF 中以曲线为主、数字摘要为辅展示 |
| 失败告警 | 生成失败记录错误摘要并通过既有 Webhook 告警 |
| 部署文档 | Docker 和离线部署材料包含报表目录、备份恢复和清理说明 |

### 10.3 验收标准

- [ ] 日报、周报、月报周期边界与 `Asia/Shanghai` 口径一致
- [ ] 总请求次数不误用 `audit_logs` 单表作为唯一来源
- [ ] 定时报表默认不导出命中片段、脱敏片段和上下文片段
- [ ] 手动生成包含敏感字段时元数据标记 `include_sensitive=true`
- [ ] 同周期同类型并发生成被任务锁或唯一约束阻止
- [ ] 日报、周报、月报以曲线展示周期内运行状态变化，不使用生成时刻快照代替周期状态
- [ ] PDF 美观、结构清晰，XLSX 多 Sheet 可筛选，CSV 可被 Excel 打开

---

## 十一、阶段 8：可观测性增强 + 告警

**当前口径**：暂不开发，仅保留规划记录；生产上线前不新增 Prometheus 指标、通用 Webhook 告警平台、图片资产后台预览/下载页面、存储配额和保留策略。审计 CSV 导出已由阶段 6B 报表中心升级承接，不再作为阶段 8 独立任务。

**规划目标**：让管理员能看到运行状态、命中趋势、拦截趋势，并在高风险事件发生时收到通知；同时增强文生图资产治理能力，在阶段 3 图片本体异步归档基础上补齐后台预览/下载页面、存储配额和保留策略。

### 9.1 任务清单

| 任务 ID | 任务 | 所属功能 | 优先级 |
|---------|------|----------|--------|
| S8-01 | 实现 Prometheus 指标：请求量、拦截量、扫描耗时、上游耗时、归档失败、告警失败、SSE 连接数 | F12 | P0 |
| S8-02 | 实现 `notify/rate_limiter.py` 告警频率控制 | F9 | P0 |
| S8-03 | 实现 `notify/webhook.py`，支持企微/飞书 Webhook | F9 | P0 |
| S8-04 | 在 `proxy/relay.py` 集成告警推送 | F9 | P0 |
| S8-05 | 编写 `tests/test_webhook.py` | F9 | P0 |
| S8-06 | 管理后台统计面板增强：拦截趋势图、Top 规则、Top Key | F12 | P0 |
| S8-07 | 审计日志 CSV 导出 | F7 | 已调整至阶段 6B 报表中心 |
| S8-08 | 基于阶段 3 `image_assets` 表增强图片资产后台预览/下载页面，下载接口必须鉴权并写入管理员操作审计，不直接暴露静态目录 | F8/F12/F14 | P1 |
| S8-09 | 增加图片资产存储配额、保留天数、清理任务和备份恢复演练 | 运维/F20 | P1 |

### 9.2 产出物

| 产出物 | 验收标准 |
|--------|---------|
| 运行指标 | 监控系统可采集请求量、命中量、延迟、错误率 |
| 告警推送 | 拦截事件 5 秒内或配置窗口内推送至 Webhook |
| 告警频控 | 同规则 5 分钟内不重复告警 |
| 仪表盘 | 展示今日请求数、拦截数、告警数、趋势、Top 规则 |
| CSV 导出 | 审计日志可按时间范围导出 |
| 图片后台访问 | 管理员可在鉴权后台预览/下载阶段 3 已归档的图片资产，不暴露未鉴权静态 URL |
| 存储治理 | 支持图片资产配额、保留天数、清理任务和备份恢复演练 |

### 9.3 验收标准

- [ ] 企微/飞书收到拦截告警消息
- [ ] 仪表盘展示今日拦截数、告警数、趋势
- [ ] 指标字段完整，能支撑生产监控
- [x] 文生图图片本体可异步保存，并记录 sha256、大小、类型和下载状态
- [ ] 管理后台可鉴权预览/下载图片资产，未授权访问被拒绝
- [ ] 图片资产配额、保留天数、清理任务和备份恢复演练通过

---

## 十一、阶段 9：临时审批 + Key 级安全策略 + 审批链

**当前口径**：暂不开发，仅保留规划记录；生产上线前不启用临时审批、Key 级安全策略、审批链路由、多级审批和超时升级。

**规划目标**：启用差异化治理能力。不同 APIKey 可绑定不同安全策略、审批链和审批人，高危规则不可降级或审批放行。

### 11.1 临时审批 MVP

| 任务 ID | 任务 | 所属功能 | 优先级 |
|---------|------|----------|--------|
| S9-01 | 启用 `approval_requests` 表 | F16 | P0 |
| S9-02 | 实现飞书/企微审批卡片 | F16 | P0 |
| S9-03 | 实现一次性令牌，绑定请求哈希与短有效期 | F16 | P0 |
| S9-04 | 审批通过后允许一次性重放脱敏后请求 | F16 | P0 |
| S9-05 | 审批动作写入审计 | F16/F7 | P0 |

### 11.2 Key 级安全策略 F18

| 任务 ID | 任务 | 所属功能 | 优先级 |
|---------|------|----------|--------|
| S9-06 | 实现 `governance/security_policy.py`：load_policy / resolve_inheritance / apply_overrides | F18 | P0 |
| S9-07 | `engine/scanner.py` 扩展为 `scan(text, policy=None)` | F18 | P0 |
| S9-08 | `rules_keyword.py` / `rules_regex.py` 支持按策略过滤规则 | F18 | P0 |
| S9-09 | `proxy/relay.py` 加载 Key 关联策略并传给 scanner | F18 | P0 |
| S9-10 | `admin/api/security-policies` CRUD，含继承校验、循环检测 | F18 | P0 |
| S9-11 | `admin/static/security_policies.html` 策略编辑页面 | F18 | P0 |
| S9-12 | 高危规则白名单、immutable_rules、blocked_rules 单元测试 | F18 | P0 |

### 11.3 审批链路由 F19

| 任务 ID | 任务 | 所属功能 | 优先级 |
|---------|------|----------|--------|
| S9-13 | 实现 `governance/approval_chain.py`：resolve_approver / on_approval_decision / on_timeout | F19 | P0 |
| S9-14 | 实现 `governance/approval_scheduler.py`，定时扫描超时审批请求 | F19 | P0 |
| S9-15 | 修改 `notify/approval_webhook.py`，按链路当前级别推送审批通知 | F19 | P0 |
| S9-16 | `admin/api/approval-chains` CRUD | F19 | P0 |
| S9-17 | `admin/static/approval_chains.html` 多级节点、超时升级配置页面 | F19 | P0 |
| S9-18 | 策略与审批链关联到 APIKey 的前端 UI 集成 | F18/F19 | P0 |

### 11.4 验收标准

- [ ] 不同 Key 可绑定不同安全策略
- [ ] 策略继承最多 3 级，循环继承被拒绝
- [ ] 高危规则不可降级、不可审批放行
- [ ] 不同部门或 Key 可路由到不同审批人
- [ ] 超时审批可升级到上级
- [ ] 策略加载 < 10ms，不影响 P95 延迟

---

## 十二、阶段 10：远期能力

**当前口径**：暂不开发，仅保留规划记录；生产上线前不启用文件安全、NER、全文搜索、配额、多上游、多租户、SSO/角色权限等远期能力。

**规划目标**：在核心产品稳定后补充增强能力，避免影响阶段 1~6 的生产主链路。

### 12.1 任务清单

| 任务 | 所属功能 | 说明 |
|------|----------|------|
| 文本类文件上传解析与扫描（TXT/MD/CSV/JSON） | F17 | 优先支持安全风险低、解析确定性强的文本格式 |
| Office/PDF 文件解析与拦截 | F17 | 需要沙箱化解析与超时保护 |
| 文件脱敏重写 MVP（TXT/CSV/DOCX） | F17 | 后续支持文件内容替换与重新生成 |
| NER 命名实体识别引擎（ONNX Runtime CPU） | F10 | 用于减少规则漏报 |
| 规则分级决策矩阵正式上线 | 全局 | 统一规则等级、动作与审批关系 |
| F20 中转站配额与速率观测 | F20 | Provider 支持时只读展示或归档中转站配额/速率状态，不在 SafetyHub 本地做资源配额拦截 |
| 多上游路由 | F15 | 按 APIKey/provider/租户路由选择上游；模型/token/能力权限仍由中转站判定 |
| 消息全文搜索 | F11 | 搜索 prompt/response 内容 |
| 对话回放 | F13 | 按时间顺序展示多轮对话 |
| 多实例部署 | 部署 | 负载均衡 + 共享存储 |
| PostgreSQL 迁移 | 存储 | 数据量接近百万条时执行 |
| 语义级安全模型 | 远期 | 微调模型判断整段对话敏感性 |
| 独立检测服务 | 远期 | gRPC 通信，与代理层解耦 |
| 多租户隔离 | 远期 | 不同部门规则、Key、审计数据隔离 |

### 12.2 验收标准

- [ ] 文件入口默认关闭或按白名单启用
- [ ] 不可解析文件默认拒绝或进入审批
- [ ] NER 不影响主链路延迟，可降级关闭
- [ ] 配额与多上游路由启用后不改变既有 APIKey 行为

---

## 十三、关键路径分析

```
阶段 1: 透传中继 + 健康检查
    │
阶段 2: 弱扫描 MVP
    │
阶段 3: 归档 + 审计 + schema 预留
    │
阶段 4: 管理员认证 + 最小后台
    │
阶段 5: APIKey 管理（K-Sync 默认）
    │
阶段 6: KeyProvider + 中转站联通
    │
阶段 6A: 单实例 Docker 生产稳定性与高并发治理
    │
    ├──────────────▶ 阶段 7: 扫描升级（暂不开发）
    │
    ├──────────────▶ 阶段 8: 可观测性 + 告警（暂不开发）
    │
    └──────────────▶ 阶段 9: 审批 + 安全策略 + 审批链（暂不开发）
                            │
                            ▼
阶段 10: 远期能力（暂不开发）
```

**当前生产上线关键路径**：阶段 1 → 阶段 2 → 阶段 3 → 阶段 4 → 阶段 5 → 阶段 6 → 阶段 6A 单实例 Docker 生产稳定性与高并发治理。

**暂停开发口径**：阶段 7、8、9、10 暂不并行推进；相关依赖关系仅作为长期规划保留，不进入当前生产上线范围。

---

## 十四、上线检查清单

### 13.1 功能性检查

- [x] 正常对话可完成（非流式 + 流式）
- [x] 请求侧手机号脱敏后再发往中转站
- [x] 保守关键词命中后返回伪装回复
- [x] 响应原样透传，不做响应脱敏
- [x] Chat 对话记录写入数据库（原始 + 脱敏两份 prompt）
- [x] 文生图元数据写入数据库，阶段 3 已异步归档图片本体和状态记录
- [x] 拦截、脱敏事件有审计记录；告警事件待阶段 8
- [x] 管理 API 已受认证保护，最近观测 API 可查看数据；最小管理后台页面已完成，APIKey 页面阶段 5 已升级为可操作页面
- [x] 管理后台包含仪表盘、拦截记录、训练样本、规则、设置、APIKey 管理、审批记录页面
- [x] Request ID、user_id、api_key_id、model、capability 能贯穿训练样本、审计和图片资产
- [x] APIKey 单条替换与 CSV 批量替换可用

### 14.2 性能检查

- [ ] 中继转发额外延迟 < 50ms
- [ ] 安全检测耗时 < 10ms/请求
- [ ] 50 并发 SSE 连接稳定
- [x] `/v1/*` 最大在途请求数受 `V1_MAX_INFLIGHT` 约束，队列满或排队超时能快速返回 429/503，自动化测试已覆盖
- [x] `/admin/*` 和 `/health/*` 不进入 `/v1/*` 队列；高并发压测期间实际响应时间仍需记录
- [ ] 上游 HTTP 连接池复用生效，连接数不随请求总数无限增长
- [x] 归档/审计写入削峰或降级不影响主链路返回
- [x] APIKey 已迁移到 PostgreSQL，运行配置已切换 PostgreSQL 并通过 `/health/ready` 数据库检查
- [ ] 策略加载 < 10ms

### 14.3 安全检查

- [ ] 绕过路径测试覆盖 URL 编码、分段、Unicode 混淆
- [ ] 日志中不包含 prompt 原文
- [x] APIKey 不以明文形式进入日志、数据库明文字段、告警和管理后台列表
- [x] 管理后台需要认证
- [x] 管理员查看详情、规则操作、Key 创建/吊销/替换动作均写入管理员操作审计；导出和审批动作待阶段 8/9 启用后补齐
- [ ] 数据库文件权限正确，仅 app 用户可读写
- [ ] 文件上传入口默认关闭或限制大小/类型
- [ ] 没有对外开放非必要端口

### 14.4 运维检查

- [ ] TLS 证书自动续签配置正确
- [ ] docker compose 配置 `restart: unless-stopped`
- [ ] 磁盘空间监控就位
- [ ] 数据保留清理任务和备份恢复演练通过
- [ ] 健康检查端点可被监控系统探测
- [ ] 基础指标覆盖请求量、拦截量、扫描耗时、上游耗时、归档失败、告警失败、SSE 连接数

---

## 十五、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| `/v1/*` 高并发压垮单实例 | 高 | 高 | 阶段 6A 引入全局有界并发队列、排队超时、队列满快速失败、生产多 worker 折算和阶梯压测；默认 4 worker 下至少覆盖容器总 `1000` in-flight + `2000` 排队目标 |
| 管理后台被压测流量拖慢 | 高 | 中 | `/admin/*` 和 `/health/*` 不进入 `/v1/*` 队列，`/admin/api/stats` 短缓存，列表默认分页轻量查询 |
| SSE 长连接压垮服务器 | 中 | 高 | 流式不单独拆分并发池，统一受 `/v1/*` 并发闸门约束；通过归档截断、连接池复用、Uvicorn worker 控制、阶段 6A 压力测试和阶段 8 指标监控缓解 |
| 规则误杀正常对话 | 中 | 中 | 阶段 2 只启用弱扫描；阶段 7 用回归测试和误报率监控再扩充 |
| 规则被绕过 | 高 | 高 | 阶段 7 专门覆盖 URL 编码、分段发送、Unicode 混淆 |
| 数据库性能瓶颈 | 高 | 高 | 当前运行库已切换 PostgreSQL；阶段 6A 继续验证连接稳定性、索引、备份恢复和归档/审计写入削峰，SQLite 仅作为兼容和回退参考 |
| Python 内存泄漏 | 低 | 中 | Uvicorn 多 worker + max-requests 自动重启 worker |
| 正则 ReDoS 攻击 | 中 | 高 | 设置匹配超时 + 恶意构造文本降级处理 |
| 上游中转站不可用 | 中 | 中 | 阶段 1 直接透传错误；阶段 6 后支持 Provider/多上游切换 |
| APIKey 明文泄露 | 中 | 高 | 只存加密值、哈希和前后缀；日志、告警、后台统一脱敏 |
| 忘记数据加密 Key | 中 | 高 | 默认 K-Sync，可从中转站或客户端配置重新录入恢复；支持批量替换 |
| 中转站替换导致客户端大规模改配置 | 中 | 高 | 阶段 5 支持单条/批量替换上游 Key，前哨站 Key 不变 |
| 权限体系后补导致重构 | 高 | 中 | 阶段 3 预留 api_key_id、model、capability、policy、approval、quota 字段 |
| function call/MCP 伪装误触发工具 | 中 | 高 | block 时只返回普通 assistant 文本，不生成 tool call，不模拟 MCP 工具结果 |
| 临时审批滥用 | 中 | 高 | 只允许可审批规则；令牌一次性、短有效期、绑定请求哈希和审批审计 |
| 文件上传绕过检测 | 高 | 高 | 阶段 10 前文件入口默认关闭或白名单启用，不可解析文件默认拒绝或审批 |

---

## 十六、版本与功能映射

| 版本 | 阶段 | 包含功能 ID | 上线标准 |
|------|------|------------|----------|
| v0.1 | 阶段 1 | F1、F14 基线 | 项目可本地启动，健康检查、Request ID、透传中继可用 |
| v0.5 | 阶段 2 | F2、F4、F5、F6、F14 | 弱扫描、安全链路、伪装回复可演示 |
| v0.7 | 阶段 3 | F3、F7、F15/F18/F19/F20 预留 | 归档、审计、schema 预留完成 |
| v0.8 | 阶段 4 | F8、F14 | 管理后台最小能力可用，管理员认证启用 |
| v1.0 | 阶段 5 | F15 | APIKey 管理、K-Sync、加密、替换能力可用，生产可上线 |
| v1.1 | 阶段 6 | F15.2 | KeyProvider、中转站联通、Provider 创建/reveal/吊销和历史 Key 导入核心能力完成 |
| v1.1.1 | 阶段 6A | F1/F3/F7/F8/F14 | 单实例 Docker 生产稳定性、高并发治理、管理端保护、连接池复用、归档削峰和压测验收 |
| v1.2 | 阶段 9 | F16、F18、F19 | 暂不开发，仅保留审批、安全策略、审批链规划 |
| v2.0+ | 阶段 10 | F10、F11、F13、F17、F20 | 暂不开发，仅保留文件安全、NER、配额、多上游、多租户等远期规划 |

---

## 十七、交付物总览（含阶段 6A 生产稳定性治理交付物）

| 交付物 | 形式 | 完成阶段 |
|--------|------|----------|
| GitHub 仓库与项目骨架 | 代码 | 阶段 1 |
| Docker Compose 一键部署 | 配置 | 阶段 1 |
| 核心中继引擎（流式/非流式透传） | 代码 | 阶段 1 |
| 健康检查、Request ID、结构化日志 | 代码/配置 | 阶段 1 |
| Header Policy 与单上游路由 | 代码 | 阶段 1 |
| 弱扫描规则集 | YAML 配置 | 阶段 2 |
| 安全检测引擎（关键词 + 正则 + 调度） | 代码 | 阶段 2 |
| 请求侧手机号脱敏 | 代码 | 阶段 2 |
| 伪装回复（OpenAI 兼容格式） | 代码 | 阶段 2 |
| 训练样本与轻量审计（messages + assistant response / 命中证据） | 代码 | 阶段 6A 当前口径 |
| 审计日志 | 代码 | 阶段 3 |
| APIKey/模型/策略/审批/配额 schema 预留 | 代码 | 阶段 3 |
| 管理后台（最小 Web 界面） | 代码 | 阶段 4 |
| 管理后台认证 | 代码 | 阶段 4 |
| 管理员操作审计 | 代码 | 阶段 4 |
| APIKey 管理（K-Sync 默认） | 代码 | 阶段 5 |
| APIKey 加密存储 | 代码 | 阶段 5 |
| 上游 Key 单条/批量替换 | 代码 | 阶段 5 |
| KeyProvider 抽象层 | 代码 | 阶段 6 |
| 中转站联通创建 Key | 代码 | 阶段 6 |
| DLP 完整规则库 | YAML 配置 | 阶段 7 |
| 规则启停与热加载 | 代码 | 阶段 2 |
| 绕过防护与完整规则回归 | 代码 | 阶段 7 |
| Prometheus 指标与仪表盘 | 代码/配置 | 阶段 8 |
| 企微/飞书告警推送 | 代码 | 阶段 8 |
| 报表中心 CSV/XLSX/PDF 导出 | 代码 | 阶段 6B |
| 临时审批 MVP | 代码 | 阶段 9 |
| Key 级安全策略 | 代码 | 阶段 9 |
| 审批链路由 | 代码 | 阶段 9 |
| 文件上传解析与拦截 | 代码 | 阶段 10 |
| NER 检测引擎 | 代码 | 阶段 10 |
| 配额、速率限制、多上游、多租户 | 代码 | 阶段 10 |
