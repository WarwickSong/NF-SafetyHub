# LLM-SafetyHub 功能定义规划

> 本文档对 SafetyHub 的全部功能进行系统性拆分与定义，明确每个功能的输入、输出、行为约束和验收标准。

---

## 一、功能总览

SafetyHub 定位为 **LLM 对话安全代理层**，位于用户客户端与中转站之间，核心职责是：

1. **透明中继** — 对用户和中转站完全透明，不改变任何协议行为
2. **安全检测** — 在请求发出前对内容进行敏感信息检测
3. **拦截伪装** — 命中规则时拦截请求并伪装为大模型正常回复
4. **核心归档** — Chat 对话的 prompt 和 response 完整归档；文生图先归档元数据，图片本体后续异步归档
5. **审计追溯** — 拦截事件独立记录，支持多维查询
6. **实时告警** — 拦截事件推送至企微/飞书
7. **治理预留** — 为 APIKey 映射、安全策略、多上游路由、临时审批提前预留数据结构和接口边界；模型权限、token 额度和资源能力权限由中转站管理
8. **文件安全** — 对上传文件进行解析、检测、拦截或脱敏预留

### 功能层级关系

```
┌─────────────────────────────────────────────────┐
│                   管理层                         │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ 管理后台  │  │ 告警通知  │  │ 审计追溯      │  │
│  └──────────┘  └──────────┘  └───────────────┘  │
├─────────────────────────────────────────────────┤
│                   检测层                         │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ 关键词匹配│  │ 正则规则  │  │ NER（后续）   │  │
│  └──────────┘  └──────────┘  └───────────────┘  │
├─────────────────────────────────────────────────┤
│                   核心层                         │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ 中继转发  │  │ 伪装回复  │  │ 消息归档      │  │
│  └──────────┘  └──────────┘  └───────────────┘  │
└─────────────────────────────────────────────────┘
```

---

## 二、核心层功能定义

### F1 — 中继转发（Relay）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F1 |
| **优先级** | P0 — 必须实现 |
| **描述** | 接收客户端请求，完整转发至中转站，再将中转站响应透传回客户端。对双方完全透明，不修改任何请求/响应内容 |

**输入**

| 输入项 | 类型 | 说明 |
|--------|------|------|
| HTTP 请求 | OpenAI-compatible `/v1/*` | 阶段 1 支持 `/v1/*` 通用代理；Chat Completions 是主要安全治理入口，非 Chat 接口默认透明透传 |
| 请求头 | Headers | 透传 Authorization、Content-Type 等，剥离高风险和内部 Header |
| 请求体 | JSON / raw body / empty | Chat 使用 `messages` 做扫描、拦截和后续脱敏；Embeddings、Completions、Responses、Images、未知接口阶段 1 默认不拦截，后续按需做脱敏或资产归档 |

**输出**

| 输出项 | 类型 | 说明 |
|--------|------|------|
| 非流式响应 | JSON | 中转站返回的完整 JSON 响应 |
| 流式响应 | SSE | 中转站返回的 SSE 事件流，逐 chunk 透传 |

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F1-C1 | pass/warn 路径不修改请求体中的任何字段；desensitize 路径仅允许按明确规则改写请求侧文本字段 |
| F1-C2 | 不修改响应体中的任何字段 |
| F1-C3 | 请求头按 Header Policy 透传，默认剥离 Host、Hop-by-hop Headers、内部管理 Header、Cookie 等高风险字段 |
| F1-C4 | 流式请求必须逐 chunk 实时转发，不得缓冲完整响应后再发送 |
| F1-C5 | 上游（中转站）断开连接时，必须正确关闭下游连接，不能挂起 |
| F1-C6 | 连接超时设置：上游连接超时 10s，读取超时 120s（LLM 生成长回复时需要） |
| F1-C7 | Chat Completions 同时支持 `stream: true` 和 `stream: false` 两种模式；其他接口按上游协议透明返回 |
| F1-C8 | 统一生成或透传 `X-Request-ID`，并写入归档、审计、告警和结构化日志 |
| F1-C9 | 用户身份与 APIKey 身份从 `RequestContext` 获取，不直接依赖原始 Authorization 字符串 |
| F1-C10 | v1.0 默认单上游转发，但路由层预留按 APIKey、模型、能力选择不同中转站的接口 |
| F1-C11 | Chat Completions 必须提取 `messages` 文本进入 Scanner；非 Chat 接口阶段 1 默认透明透传，不因敏感词命中而拦截 |
| F1-C12 | Embeddings、Completions、Responses、Images、未知 `/v1/*`、非 JSON、multipart、二进制请求默认透明透传；后续仅按明确业务需要增加脱敏或资产归档 |

**验收标准**

- [ ] Chat 非流式请求：客户端收到与直连中转站完全一致的响应
- [ ] Chat 流式请求：SSE 事件逐个实时到达，延迟 < 50ms（相比直连）
- [ ] `POST /v1/embeddings`、`POST /v1/completions`、`POST /v1/responses`、`POST /v1/images/*` 等非 Chat 接口可透明透传，不因敏感词命中而拦截
- [ ] `GET /v1/models` 可透明透传并保留查询参数
- [ ] 未知 `/v1/*` 请求可默认透明透传，后续仅按明确业务需要增加脱敏或资产归档
- [ ] 上游断开时客户端连接正确关闭，无挂起
- [ ] 50 并发 SSE 连接稳定运行 5 分钟无异常

---

### F2 — 伪装回复（Fake Response）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F2 |
| **优先级** | P0 — 必须实现 |
| **描述** | 当请求被拦截时，生成一条伪装为大模型正常回复的安全提示，使客户端体验无感知 |

**输入**

| 输入项 | 类型 | 说明 |
|--------|------|------|
| 拦截结果 | ScannerResult | 包含命中规则 ID、规则级别、命中文本片段 |
| 原始请求 | JSON | OpenAI 请求体，用于判断是否为流式请求 |

**输出**

| 输出项 | 类型 | 说明 |
|--------|------|------|
| 非流式伪装响应 | JSON | 符合 OpenAI 响应格式的 JSON |
| 流式伪装响应 | SSE | 模拟流式输出的 SSE 事件序列 |

**伪装响应格式**

非流式：
```json
{
  "id": "chatcmpl-safetyhub-xxxxx",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "安全策略系统",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "抱歉，我无法处理您的请求。您输入的内容可能包含敏感信息，请检查后重试。如需帮助，请联系信息安全团队。"
    },
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
}
```

流式：逐 token 输出上述 content，每个 chunk 包含 1-2 个字符，模拟打字效果。

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F2-C1 | 伪装响应必须完全兼容当前请求使用的 OpenAI API 响应格式，客户端无法区分与正常回复的区别 |
| F2-C2 | 提示内容不得泄露具体命中的规则名称或敏感信息片段 |
| F2-C3 | 流式伪装的 token 输出间隔应模拟真实模型（约 30-80ms/chunk） |
| F2-C4 | 伪装回复的 model 字段应与用户请求的 model 字段一致 |
| F2-C5 | 支持可配置的回复模板（不同规则级别可返回不同提示语） |
| F2-C6 | 对 `tools` / `function_call` 请求默认返回普通 assistant 文本，不主动生成工具调用，避免触发客户端执行外部函数 |
| F2-C7 | 对 MCP 工具调用能力默认视为高风险 capability，v1.0 仅透传请求体并做输入扫描，不模拟 MCP 工具结果 |
| F2-C8 | 对 reasoning / think 类模型，伪装回复默认不输出推理过程，不构造 `<think>` 内容，仅返回最终安全提示 |
| F2-C9 | 若未来支持 Responses API、Assistants API 或多模态协议，伪装层必须按 endpoint 维护协议适配器，不能只复用 chat.completions 格式 |

**验收标准**

- [ ] 非流式伪装响应被 OpenAI SDK 正常解析
- [ ] 流式伪装响应在 ChatGPT-Next-Web 等客户端上正常显示
- [ ] 提示内容不含任何敏感信息片段
- [ ] 不同规则级别返回不同提示语

---

### F3 — 消息归档（Message Archive）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F3 |
| **优先级** | P0 — 必须实现 |
| **描述** | Chat 对话的 prompt 和 response 完整记录到 SQLite，支持按用户/时间/关键词检索；阶段 3 同步记录文生图元数据但不保存图片本体 |

**输入**

| 输入项 | 类型 | 说明 |
|--------|------|------|
| 请求信息 | ArchiveRequest | 用户 ID、请求时间、prompt 内容、model、stream 标志 |
| 响应信息 | ArchiveResponse | 响应内容、响应时间、token 用量、是否被拦截 |
| 文生图元数据 | ImageGenerationMetadata | prompt、model、size、style、n、response URL 或 b64 存在状态、request_id、用户、时间；阶段 3 不保存图片本体 |

**存储模型**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| request_id | TEXT UNIQUE | 请求唯一标识（UUID） |
| user_id | TEXT | 用户标识（来自 RequestContext） |
| api_key_id | TEXT | APIKey 记录 ID，阶段 3 可为空但字段预留 |
| model | TEXT | 请求的模型名称 |
| capability | TEXT | 请求能力类型，如 chat / file_upload / function_call / mcp_tool / reasoning |
| prompt | TEXT | 当前实际转发的 messages JSON，兼容旧字段；新逻辑优先使用 prompt_desensitized |
| prompt_original | TEXT | 原始 Chat messages JSON，用于上线观测和误报分析 |
| prompt_desensitized | TEXT | 脱敏后 Chat messages JSON，即发往上游的请求侧上下文 |
| response | TEXT | 完整的响应内容；阶段 3 第一版中流式响应暂以 `{stream: true}` 占位，完整拼接后续补齐 |
| is_stream | BOOLEAN | 是否流式请求 |
| is_blocked | BOOLEAN | 是否被拦截 |
| is_desensitized | BOOLEAN | 是否发生请求侧脱敏改写 |
| action_taken | TEXT | passed / desensitized / warned / blocked |
| blocked_rule_id | TEXT | 命中的 block 规则 ID（未拦截为空） |
| matched_rule_ids | TEXT | 命中规则 ID 列表 JSON |
| approval_id | TEXT | 临时审批记录 ID，无审批为空 |
| file_ids | TEXT | 关联文件扫描记录 ID 列表 |
| image_metadata | TEXT | 文生图元数据 JSON，阶段 3 仅记录 prompt、参数和响应引用，不保存图片本体 |
| prompt_tokens | INTEGER | prompt token 数 |
| completion_tokens | INTEGER | completion token 数 |
| created_at | DATETIME | 请求时间 |
| completed_at | DATETIME | 响应完成时间 |
| latency_ms | INTEGER | 响应耗时（毫秒） |

**查询接口**

| 接口 | 方法 | 说明 |
|------|------|------|
| `/admin/api/archives` | GET | 分页查询，支持 user_id / time_range / keyword 筛选 |
| `/admin/api/archives/{id}` | GET | 单条记录详情，含完整 prompt 和 response |
| `/admin/api/archives/stats` | GET | 统计概览（总量、按用户统计、按时间趋势） |

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F3-C1 | 归档写入必须异步，不能阻塞请求转发流程 |
| F3-C2 | 流式响应必须在最后一个 chunk 到达后拼接完整响应再归档 |
| F3-C3 | 归档失败（如数据库写入异常）不能影响正常转发 |
| F3-C4 | prompt 字段存储完整的 messages JSON，不截断 |
| F3-C5 | 查询接口支持分页，默认每页 20 条，最大 100 条 |
| F3-C6 | 敏感字段（prompt、response）在查询接口返回时默认脱敏，详情接口才返回完整内容 |
| F3-C7 | 阶段 3 文生图只记录元数据和响应引用，不下载、不解码、不保存图片本体 |
| F3-C8 | 图片本体异步归档、后台预览/下载、存储配额和保留策略统一放到阶段 8 实现 |
| F3-C9 | 上线初期提供临时管理侧观测窗口，可查看数据库中最近若干条完整 Chat 对话记录，包含原始 messages、role、脱敏后 messages、响应、命中动作和命中规则，用于验证真实 Agent 消息组装与误报情况 |
| F3-C10 | 临时观测窗口必须默认限制为最近少量记录，要求管理认证，仅用于上线验证；后续由正式归档/审计详情页替代，并按权限、脱敏展示和保留策略收敛 |

**验收标准**

- [x] Chat 非流式正常请求、脱敏请求、拦截请求可写入归档，包含原始/脱敏 messages、动作和规则 ID
- [x] 归档失败不影响请求主链路
- [x] 最近观测 API 可读取最近少量完整 Chat 样本
- [x] 流式 Chat 请求的响应内容完整拼接后归档
- [x] 文生图请求能记录元数据和响应引用，且阶段 3 不保存图片本体
- [x] 正式归档分页查询支持 user_id / 时间范围 / 关键词筛选
- [ ] 分页查询性能在 10 万条数据时 < 200ms

---

## 三、检测层功能定义

### F4 — 关键词规则检测（Keyword Scanner）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F4 |
| **优先级** | P0 — 必须实现 |
| **描述** | 基于关键词库对请求内容进行匹配检测，支持精确匹配和模糊匹配 |

**输入**

| 输入项 | 类型 | 说明 |
|--------|------|------|
| 扫描文本 | str | 由调用方传入的请求侧文本；Chat block 判定阶段默认传入最新一条允许扫描 role 的有文本 message，脱敏阶段仅覆盖允许脱敏 role 的 messages |
| 规则配置 | YAML | 关键词规则库 |

**规则配置格式**

```yaml
keyword_rules:
  - id: "KW-001"
    name: "商业机密-产品路线图"
    keywords: ["产品路线图", "roadmap", "产品规划"]
    level: "block"          # block / warn / pass
    match_mode: "contains"  # contains / exact / prefix
    case_sensitive: false
    description: "拦截包含产品路线图相关关键词的对话"

  - id: "KW-002"
    name: "凭据-密码明文"
    keywords: ["password=", "passwd=", "密码是"]
    level: "block"
    match_mode: "contains"
    case_sensitive: true
    description: "拦截包含明文密码的对话"
```

**输出**

| 输出项 | 类型 | 说明 |
|--------|------|------|
| 扫描结果 | ScannerResult | 命中规则列表（可能多个）、命中位置、匹配文本片段 |

**ScannerResult 结构**

```python
@dataclass
class ScannerResult:
    hit: bool                    # 是否命中
    rule_id: str                 # 命中的规则 ID
    rule_name: str               # 规则名称
    level: str                   # block / warn / pass
    matched_text: str            # 匹配到的文本片段（脱敏后存储）
    position: tuple[int, int]    # 命中文本在原文中的起止位置
    scanner_type: str            # "keyword" / "regex" / "ner"
```

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F4-C1 | 关键词 Scanner 只负责检测调用方传入文本，不内置 messages 范围假设；Chat block 调用方默认只传入最新一条允许扫描 role 的有文本 message |
| F4-C2 | 单条文本可能命中多条规则，所有命中结果都需返回 |
| F4-C3 | 规则配置修改后热加载生效，无需重启服务 |
| F4-C4 | 关键词匹配耗时 < 1ms/请求 |
| F4-C5 | `case_sensitive: false` 时统一转为小写后匹配 |

**验收标准**

- [x] 初版关键词库 ≥ 20 条规则，其中阶段 2 默认启用 5 条极保守 block 规则，其余扩展规则默认关闭
- [x] 修改 YAML 后 5 秒内新规则生效
- [x] 中文和英文关键词均能正确匹配
- [x] 多条规则同时命中时全部返回

---

### F5 — 正则规则检测（Regex Scanner）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F5 |
| **优先级** | P0 — 必须实现 |
| **描述** | 基于正则表达式对请求内容进行模式匹配，检测手机号、身份证号、银行卡号、邮箱、API Key 等结构化敏感信息 |

**规则配置格式**

```yaml
regex_rules:
  - id: "RG-PHONE-CN"
    name: "PII-中国手机号"
    pattern: "(?<!\\\\d)1[3-9]\\\\d{9}(?!\\\\d)"
    level: "desensitize"
    replacement: "phone"
    description: "阶段 2 中国大陆手机号脱敏"

  - id: "RG-EXPANSION-001"
    name: "PII-身份证号"
    pattern: "[1-9]\\d{5}(19|20)\\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\\d|3[01])\\d{3}[\\dXx]"
    level: "block"
    description: "检测18位身份证号"

  - id: "RG-003"
    name: "凭据-API Key"
    pattern: "(sk|pk|ak)_[a-zA-Z0-9]{20,}"
    level: "block"
    description: "检测常见 API Key 格式"

  - id: "RG-004"
    name: "凭据-邮箱"
    pattern: "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}"
    level: "warn"
    description: "检测邮箱地址（告警级别，可能为正常业务邮箱）"
```

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F5-C1 | 正则编译在规则加载时完成，运行时不重复编译 |
| F5-C2 | 单条正则匹配超时 100ms，超时视为未命中（防止 ReDoS） |
| F5-C3 | 正则匹配耗时 < 5ms/请求（正常模式，非恶意构造文本） |
| F5-C4 | 规则配置修改后热加载生效，无需重启服务 |
| F5-C5 | 初版正则规则 ≥ 10 个模式 |

**验收标准**

- [x] 阶段 2 默认启用的手机号规则能正确检出并脱敏，身份证号、银行卡号、邮箱、API Key 等扩展规则已预留但默认关闭
- [x] 阶段 2 弱规则集普通文本无误报
- [x] 规则热加载 5 秒内生效
- [x] 后台可启停单条规则，启停后立即热加载
- [x] ReDoS 攻击文本不导致服务卡顿

---

### F6 — 扫描器调度引擎（Scanner Orchestrator）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F6 |
| **优先级** | P0 — 必须实现 |
| **描述** | 统一调度所有 Scanner，按链式顺序依次调用，任一 Scanner 命中 block 级别即拦截 |

**调度策略**

```
请求文本 → Keyword Scanner → Regex Scanner → [NER Scanner（后续）]
                 │                  │
                 ├─ hit(block) ───→ 拦截，返回伪装回复
                 ├─ hit(warn)  ───→ 记录告警，继续放行
                 └─ miss      ───→ 传递到下一个 Scanner
```

**分级策略**

| 级别 | 行为 | 说明 |
|------|------|------|
| `block` | 拦截请求 + 伪装回复 + 记录审计 + 触发告警 | 确定的敏感信息，绝不允许外泄 |
| `warn` | 放行请求 + 记录审计 + 触发告警 | 疑似敏感信息，需人工复核 |
| `pass` | 仅记录 | 命中但为已知的正常模式（白名单） |

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F6-C1 | Scanner 调用顺序可配置（YAML 中定义优先级） |
| F6-C2 | block 级别命中立即返回，不再调用后续 Scanner |
| F6-C3 | 多个 warn 级别命中需汇总所有结果 |
| F6-C4 | 扫描器异常不能导致请求失败，降级为放行并记录错误日志 |
| F6-C5 | 全流程扫描耗时 < 10ms/请求 |

**验收标准**

- [x] block 规则命中时请求被拦截，不发出到中转站
- [ ] warn 规则当前默认未启用，启用后沿用命中审计链路
- [x] Scanner 异常时请求正常放行，错误被记录
- [x] 链式调度顺序可通过配置修改

---

### F6.1 — 弱扫描 MVP 与渐进式上线（阶段 2 / 阶段 7）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F6.1 |
| **优先级** | P0 — 阶段 2 必须实现 |
| **描述** | 阶段 2 上线时仅启用极保守的扫描规则集（手机号脱敏 + 3-5 条几乎不会触发的关键词），完整的扫描链路（normalizer + scanner + 脱敏 + 伪装回复）已经就绪，规则集在阶段 7 升级为完整版本 |

**阶段 2 规则集（弱扫描 MVP）**

| 规则类型 | 规则 ID | 行为 | 说明 |
|---------|--------|------|------|
| 正则 | RG-PHONE-CN | desensitize | 中国大陆手机号 `1[3-9]\d{9}` → 替换为 `138****1234` 格式 |
| 正则 | RG-PHONE-INTL | desensitize | 国际电话格式 → 替换为脱敏格式 |
| 关键词 | KW-CONFIDENTIAL-1 | block | "告诉你一个公司机密" |
| 关键词 | KW-CONFIDENTIAL-2 | block | "保密协议内容" |
| 关键词 | KW-CONFIDENTIAL-3 | block | "这是绝密文件" |
| 关键词 | KW-CONFIDENTIAL-4 | block | "请记住以下密钥" |
| 关键词 | KW-CONFIDENTIAL-5 | block | "不要告诉别人" |

**阶段 7 升级（完整规则集）**

| 规则类型 | 数量 | 覆盖维度 |
|---------|------|---------|
| 正则 | 30+ | 手机号、姓名、地址、身份证、信用卡、邮箱、银行卡、IP、URL、API Key 等 |
| 关键词 | 20+ | 商业机密、技术机密、人事机密、客户名单、财务数据等 |

**低干扰优先原则**

阶段 2 和上线初期优先保证用户可用性，安全策略采用最低必要干预：只在高置信、低误报规则下触发 block 或 desensitize；对 role、协议结构或来源不确定的内容，默认放行并依赖归档/审计观察，不扩大拦截和脱敏范围。后续是否扩大规则、role 或非 Chat 接口覆盖范围，必须以真实归档样本和误报分析为依据。

**扫描方向：仅请求侧（不做响应脱敏）**

```text
客户端 prompt/messages
  ↓
SafetyHub: 请求侧处理
  ├─ block 判定：仅扫描 Chat messages 中最新一条允许扫描 role 的有文本内容 message；命中后不发往中转站，返回伪装回复
  ├─ desensitize 改写：仅对 Chat 中允许脱敏 role 的文本字段执行脱敏；脱敏后版本转发到中转站
  └─ pass：未命中 block 且无需脱敏时原样转发
  ↓
中转站收到的内容已经是脱敏后的版本
  ↓
中转站响应 → 原样透传给客户端（响应不脱敏，不破坏 RAG/网络检索等场景）
```

**Chat role 处理范围说明**

| role | block 判定 | desensitize 改写 | 说明 |
|------|------------|------------------|------|
| `user` | 参与 | 参与 | 用户上传内容，是主要外泄来源 |
| `tool` | 参与 | 参与 | Agent 读取文件、命令输出、工具结果，外泄风险高 |
| `function` | 参与 | 参与 | 兼容旧式 function call 结果 |
| `assistant` | 不参与 | 不参与 | 避免拦截或改写大模型历史回复中的有效业务内容 |
| `system` | 不参与 | 不参与 | 避免前哨站干扰系统提示词和业务编排 |
| `developer` | 不参与 | 不参与 | 避免前哨站干扰开发者提示词和业务编排 |

- 阶段 2 不记录会话历史，不做 message fingerprint；为避免历史敏感词导致多轮对话粘滞拦截，block 只看当前请求尾部最新一条允许扫描 role 的有文本内容 message。
- 如果请求尾部存在不允许扫描的 role、空 content 或非文本 content，则向前寻找最近一条允许扫描 role 的有文本内容 message。
- 脱敏与 block 范围不同：脱敏覆盖所有允许脱敏 role 的 messages，但跳过 `assistant`、`system`、`developer`，避免过度干扰正常使用。

**协议与 Agent 适配依据**

- OpenAI-compatible Chat Completions 工具调用链路中，模型先以 `assistant` 消息返回 `tool_calls`，应用执行工具后再把结果作为 `role: "tool"` 的消息追加到后续请求；因此 `tool` 应参与 block 与脱敏。
- Anthropic Claude Messages API 只有 `user` / `assistant` 对话 role，工具结果以 `tool_result` content block 放在 `user` 消息中回传；因此 `user` 需要参与 block 与脱敏，且不能只依赖 `tool` role 覆盖 Agent 结果。
- Codex/Claude Code/Trae Agent 等编码 Agent 通常采用“模型输出工具调用 → 本地执行读取文件/终端命令/编辑操作 → 把结果追加回下一次模型请求”的 agent loop；因此最新允许 role 的尾部输入更适合 MVP block 判定。
- OpenAI Responses API、Gemini Interactions/API 等新接口可能不使用 Chat `messages.role` 形态，而使用 `input` item、`function_call_output`、`functionResponse`、`tool_result` 等结构；阶段 2 仅固化 Chat Completions role 策略，后续扩展非 Chat 接口时必须按协议补充独立提取与脱敏规则。

**为什么不做响应脱敏？**

- SafetyHub 立项目标是"防止敏感信息从企业内部外流到外部大模型"，方向是单向的
- 模型从训练数据或公开数据返回的电话号码、地址等是公开信息，脱敏会破坏 RAG、网络检索、客户支持等正常场景
- 用户输入的 PII 已经在请求侧被替换，中转站不会接收原始 PII

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F6.1-C1 | 阶段 2 上线规则集必须保证日常对话零误报（关键词必须是"几乎不会被普通对话触发"的） |
| F6.1-C1a | 上线初期以低干扰为最高优先级；对不确定 role、协议结构、内容来源或规则置信度不足的情况默认放行，不主动扩大 block/desensitize 范围 |
| F6.1-C2 | 阶段 2 完整链路（scanner + 脱敏 + 伪装回复）必须就绪，规则集是唯一的"开关" |
| F6.1-C3 | 阶段 7 升级规则集时不修改 scanner 接口，只改 `rules_config.yaml` 和补充扫描器实现 |
| F6.1-C4 | 脱敏行为仅作用于请求侧（prompt），响应原样透传，禁止修改响应内容 |
| F6.1-C5 | 脱敏后的 prompt 是发往中转站的实际内容；阶段 3 归档表必须同时存储原始 prompt 和脱敏后 prompt 两份 |
| F6.1-C6 | 阶段 3 起命中事件无论级别（pass/desensitize/warn/block）都写入 `audit_logs`，便于规则误报分析 |
| F6.1-C7 | Chat block 判定默认只扫描最新一条允许扫描 role 的有文本 message；`assistant`、`system`、`developer` 不参与 block 判定 |
| F6.1-C8 | Chat desensitize 默认仅改写 `user`、`tool`、`function` 文本字段；`assistant`、`system`、`developer` 不脱敏，避免干扰有效回复和提示词编排 |

**验收标准（阶段 2）**

- [x] `user`、`tool`、`function` 中的手机号在请求中被替换为脱敏格式后才转发到中转站
- [x] `assistant`、`system`、`developer` 中的手机号不做脱敏改写
- [x] 最新一条允许扫描 role 的有文本 message 命中 5 条保守关键词后返回伪装回复，不发往中转站
- [x] 历史 message 命中过 block 关键词但最新 message 安全时，不发生粘滞拦截
- [x] 普通对话（"今天天气不错"、"帮我写一段 Python 代码"）零误报
- [x] 响应原样透传，不做响应侧脱敏
- [x] 阶段 2 默认规则集只启用手机号 desensitize 与 5 条极保守关键词 block
- [x] 阶段 2 支持后台规则启停，启停控制规则是否参与扫描
- [x] 阶段 2 支持规则定时热加载和后台手动热加载

**验收标准（阶段 3 衔接）**

- [x] 命中事件全部写入 audit_logs，包含 block/desensitize；warn 规则启用后沿用同一审计写入链路
- [x] 归档表同时存储原始 prompt 和脱敏后 prompt 两份

**验收标准（阶段 7）**

- [ ] 正则规则扩充到 30+ 条，覆盖完整 PII 类型
- [ ] 关键词扩充到 20+ 条
- [ ] 普通对话误报率 < 0.1%
- [ ] 命中分级（pass/desensitize/warn/block）全部能正确触发对应行为
- [ ] 完整规则集扩容后，阶段 2 已完成的规则启停与热加载机制仍稳定生效

---

## 四、管理层功能定义

### F7 — 审计追溯（Audit Log）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F7 |
| **优先级** | P1 — 第二阶段实现 |
| **描述** | 拦截事件独立记录，包含命中规则、原始文本片段、操作时间，支持多维查询和导出 |

**存储模型**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| request_id | TEXT FK | 关联消息归档记录 |
| user_id | TEXT | 用户标识 |
| rule_id | TEXT | 命中的规则 ID |
| rule_name | TEXT | 规则名称 |
| rule_level | TEXT | block / warn |
| scanner_type | TEXT | keyword / regex / ner |
| matched_snippet | TEXT | 命中的文本片段（脱敏后） |
| full_text_hash | TEXT | 原始文本 SHA256 摘要（不存储原文） |
| action_taken | TEXT | blocked / warned / passed |
| created_at | DATETIME | 事件时间 |

**查询接口**

| 接口 | 方法 | 说明 |
|------|------|------|
| `/admin/api/audits` | GET | 分页查询，支持 user_id / rule_id / level / time_range 筛选 |
| `/admin/api/audits/{id}` | GET | 单条审计详情 |
| `/admin/api/audits/export` | GET | 导出 CSV/JSON |

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F7-C1 | 审计记录不可修改、不可删除（仅追加） |
| F7-C2 | 原始敏感文本不直接存储，仅存脱敏后的片段和哈希 |
| F7-C3 | 审计写入必须异步，不阻塞主流程 |
| F7-C4 | 导出功能支持时间范围筛选，单次导出上限 10000 条 |

**验收标准**

- [ ] 每次拦截/告警事件都有独立审计记录
- [ ] 按用户、规则、级别、时间范围筛选结果正确
- [ ] 审计记录无法被修改或删除
- [ ] CSV 导出文件格式正确，可在 Excel 中打开

---

### F8 — 管理后台（Admin Dashboard）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F8 |
| **优先级** | P1 — 第二阶段实现 |
| **描述** | 提供 Web 界面供管理员查询拦截记录、查看统计、管理规则配置 |

**页面列表**

| 页面 | 路径 | 功能 |
|------|------|------|
| 仪表盘 | `/admin/` | 概览统计：今日拦截数、告警数、活跃用户、拦截趋势 |
| 拦截记录 | `/admin/blocks` | 拦截事件列表，支持筛选和查看详情 |
| 消息归档 | `/admin/archives` | 对话记录列表，支持搜索和回放 |
| 规则管理 | `/admin/rules` | 查看/新增/修改/禁用规则（后续迭代） |
| 系统设置 | `/admin/settings` | Webhook 配置、告警频率、系统参数 |

**技术方案**

- 前端：单 HTML + 原生 JavaScript + CSS（轻量，不引入 React/Vue 全家桶）
- 后端：FastAPI 路由 + Pydantic 模型
- 认证：基础认证（Basic Auth）或 IP 白名单

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F8-C1 | 管理后台必须通过认证才能访问（不能裸奔） |
| F8-C2 | 前端静态文件由 Nginx 直接服务，不经过 Uvicorn |
| F8-C3 | API 接口遵循 RESTful 规范 |
| F8-C4 | 列表页支持分页，默认 20 条/页 |

**验收标准**

- [ ] 仪表盘展示今日拦截数、告警数、拦截趋势
- [ ] 拦截记录可按用户/规则/时间筛选
- [ ] 消息归档可搜索和查看详情
- [ ] 管理后台需认证后才能访问

---

### F9 — 告警通知（Webhook Alert）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F9 |
| **优先级** | P1 — 第二阶段实现 |
| **描述** | 拦截事件实时推送至企微/飞书，含命中规则和摘要信息，支持频率控制防止告警风暴 |

**告警内容模板**

```
🚨 LLM-SafetyHub 安全告警

时间：2024-01-15 14:30:00
用户：zhangsan
规则：[KW-001] 商业机密-产品路线图
级别：BLOCK
命中片段：...产品路线图...（脱敏）
请求ID：req-xxxx-xxxx
```

**频率控制**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 同规则静默期 | 5 分钟 | 同一规则 5 分钟内只告警一次 |
| 同用户静默期 | 2 分钟 | 同一用户 2 分钟内只告警一次 |
| 全局告警上限 | 50 条/小时 | 超过则暂停告警并通知管理员 |

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F9-C1 | 告警推送必须异步，不能阻塞请求处理 |
| F9-C2 | 推送失败时本地记录，不重试（避免延迟累积） |
| F9-C3 | 告警内容不得包含完整的敏感信息原文 |
| F9-C4 | 支持企微和飞书两种 Webhook 格式 |
| F9-C5 | Webhook URL 通过环境变量配置，不硬编码 |

**验收标准**

- [ ] 拦截事件在 5 秒内推送至企微/飞书
- [ ] 同规则 5 分钟内不重复告警
- [ ] 推送失败不影响主流程
- [ ] 告警内容不含敏感信息原文

---

### F14 — 基础治理与运行基线（Governance Baseline）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F14 |
| **优先级** | P0 — 必须预留 |
| **描述** | 提供 Request ID、身份上下文、Header Policy、配置校验、数据保留、健康检查和基础指标，保障生产可运维 |

**核心能力**

| 能力 | 说明 |
|------|------|
| RequestContext | 统一包含 request_id、user_id、api_key_id、model、capability、client_ip |
| Header Policy | 控制哪些 Header 可透传、哪些必须剥离、Authorization 是否替换为上游 Key |
| 配置校验 | 启动时校验必要配置、弱密码、路径权限和生产危险默认值 |
| 健康检查 | `/health/live` 判断进程，`/health/ready` 判断数据库、规则、上游配置 |
| 指标与日志 | 暴露基础 metrics，输出结构化日志，禁止 prompt/response 原文进入运行日志 |
| 数据保留 | 支持归档 TTL、审计 TTL、清理任务和备份恢复策略 |
| 图片资产治理 | 阶段 8 支持文生图图片本体异步归档、后台预览/下载、存储配额、保留天数和清理任务 |

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F14-C1 | 每个请求必须有唯一 `request_id`，并贯穿所有日志、存储与告警 |
| F14-C2 | APIKey 不得明文入库或输出到日志，仅允许存储哈希与部分前后缀 |
| F14-C3 | 管理员查看详情、导出、规则修改、审批操作必须写入管理员操作审计 |
| F14-C4 | 生产环境缺少关键配置时必须启动失败，而不是使用不安全默认值 |
| F14-C5 | 数据清理不得删除审计必要字段，清理动作本身必须记录操作日志 |
| F14-C6 | 图片资产下载必须异步执行并限制协议、域名/IP、重定向、文件大小和 MIME 类型，避免 SSRF 与磁盘耗尽 |
| F14-C7 | 图片本体不得直接暴露为未鉴权静态文件，预览/下载必须经过管理后台鉴权和操作审计 |

---

### F15 — APIKey 映射、安全策略与多上游路由预留（Access Mapping）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F15 |
| **优先级** | P1 — v1.0 预留，v1.1 实现 |
| **描述** | 为 APIKey 到中转站映射、SafetyHub 安全策略、多上游路由提前预留结构，v1.0 不阻塞核心链路；模型权限、token 额度、速率限制和资源能力权限由中转站作为权威系统管理 |

**治理维度**

| 维度 | 示例 | v1.0 行为 | 后续行为 |
|------|------|-----------|----------|
| APIKey 映射 | `sk-xxx` | 仅预留字段，可为空 | 校验本地记录有效性、绑定 owner、加密保存 upstream_key、支持吊销和替换 |
| 请求模型 | `gpt-4o` / `deepseek-r1` | 记录请求模型 | 用于归档、审计、统计和安全策略判断；资源权限仍由中转站判定 |
| 请求能力 | chat / file_upload / function_call / mcp_tool / reasoning | 识别并记录 capability | 用于安全策略、审批和审计；资源能力授权仍由中转站判定 |
| 上游 | 默认中转站 | 单上游 | 按 APIKey/provider/路由策略选择上游，但不接管中转站模型/token 权限 |

**设计结论**

- 需要提前预留开发冗余，否则后续做 APIKey 映射、安全策略和多上游路由会重构归档、审计、告警和管理后台
- 阶段 1~3 不实现完整授权决策，只要求数据模型、接口字段、管理后台入口和 `RequestContext` 就位
- 阶段 5 开始实现 APIKey 映射、K-Sync 加密存储和上游 Key 替换；阶段 6 再实现 Provider 联通和多上游路由
- 模型权限、token 额度、速率限制和资源能力权限由中转站作为权威系统管理，SafetyHub 不做模型/能力 allowlist 拦截，相关字段不进入当前 schema、后台表单和 API 响应

#### F15.1 — 阶段 1~3 透传模式与预留点

> 背景：阶段 1~3 SafetyHub 不创建、不验证、不映射 APIKey，客户端 `Authorization` 头**原样透传**给中转站。但为了避免阶段 5 启用 APIKey 管理时改动核心链路代码，必须在阶段 3 之前完成 3 个轻量级预留：

| 预留点 | 文件 | 当前行为 | 未来行为 |
|--------|------|---------|---------|
| **P1：Authorization 替换接口** | `proxy/header_policy.py` + `proxy/relay.py` | `build_upstream_headers(headers, request_id, upstream_api_key=None)` 新增 `upstream_api_key` 参数；当前传 `None` 表示透传 | 当 `upstream_api_key` 非空时剥离原始 Authorization，替换为中转站真实 Key |
| **P2：APIKey 数据表** | `storage/models.py` | 新建 `api_keys` 表（含 `key_hash`、`key_prefix`、`provider_name`、`upstream_key_id`、`upstream_key_encrypted`、`is_active`、`expires_at` 等字段，不包含 `model_allowlist`、`capability_allowlist`、配额或速率限制字段），通过 `create_all` 一并建表，但暂不写入 | 阶段 5 由 `KeyService` 写入和查询，作为 SafetyHub Key ↔ 中转站 Key 的映射表，不作为中转站资源权限源 |
| **P3：Provider 类型配置** | `config.py` | 新增 `key_provider_type: str = "passthrough"` 配置项，启动时不读取也不校验 | 阶段 6 由工厂方法根据该值实例化 `StaticKeyProvider` / `OneApiKeyProvider` / `OpenAICompatProvider` 等具体实现 |

**阶段 1~3 透传模式下的请求路径**

```
客户端                    SafetyHub                            中转站
  │                         │                                   │
  │── Authorization:       │                                   │
  │   Bearer sk-xxx ──────→│                                   │
  │                         │── header_policy 过滤              │
  │                         │   upstream_api_key=None           │
  │                         │── 原样透传 Authorization ────────→│
  │                         │                                   │── 中转站验证 sk-xxx
```

**阶段 5/6 启用后的请求路径**

```
客户端                       SafetyHub                          中转站
  │                          │                                   │
  │── Authorization:        │                                   │
  │   Bearer sk-sh-xxx ────→│                                   │
  │                          │── identity 中间件解析             │
  │                          │   → ApiKey 表查询 → 解密获取       │
  │                          │     上游真实 Key sk-real-yyy      │
  │                          │── header_policy 过滤              │
  │                          │   upstream_api_key=sk-real-yyy    │
  │                          │── 替换 Authorization 后转发 ────→│
  │                          │                                   │── 中转站验证 sk-real-yyy
```

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F15.1-C1 | 阶段 3 之前三个预留点的引入不得改变现有透传行为，单元测试需覆盖 `upstream_api_key=None` 时的等价性 |
| F15.1-C2 | `api_keys` 表在阶段 3 必须存在但允许为空；不得在生产环境出现明文 Key 写入 |
| F15.1-C3 | `key_provider_type` 默认 `passthrough`，阶段 1~5 取任何其他值都不会改变行为，阶段 6 才启用 Provider 工厂 |
| F15.1-C4 | 归档 `api_key_id` 字段在透传模式下默认存空字符串或 Authorization 哈希前缀，但禁止存入完整 Key |

#### F15.1.5 — K-Sync 与 K-Decoupled 模式（阶段 5 默认 K-Sync）

> 背景：阶段 5 启用 APIKey 管理时，**默认让 SafetyHub Key 与中转站 Key 一致（K-Sync）**，以最大化"Key 丢失也能找回"的可恢复性。同时保留 K-Decoupled 实现路径，便于后续中转站替换或安全升级。

| 模式 | 客户端使用的 Key | SafetyHub 数据库存储 | 适用场景 |
|------|---------------|-------------------|---------|
| **K-Sync** | `sk-real-xxx`（中转站 Key） | `key_hash = hash(sk-real-xxx)`，`upstream_key_encrypted = encrypt(sk-real-xxx)` | 阶段 5 默认；客户端历史 Key 直接录入即可使用；丢失后可从客户端配置或中转站找回 |
| **K-Decoupled** | `sk-sh-xxx`（SafetyHub 随机生成） | `key_hash = hash(sk-sh-xxx)`，`upstream_key_encrypted = encrypt(sk-real-yyy)` | 阶段 6+ 启用；中转站 Key 一旦发生过替换的记录自动切换到此模式；客户端 Key 与中转站 Key 解耦 |

**自动模式升级规则**

```
新建 ApiKey 时          → K-Sync 模式（hash(safetyhub_key) == hash(upstream_key)）
                          ApiKeyRecord.is_decoupled = False

替换上游 Key 后         → K-Decoupled 模式（safetyhub_key 不变，upstream_key 变化）
                          ApiKeyRecord.is_decoupled = True
                          客户端无感切换
```

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F15.1.5-C1 | K-Sync 模式下，`safetyhub_key` 和 `upstream_key` 必须在同一事务内创建，禁止只写其中一个 |
| F15.1.5-C2 | K-Sync 模式下 `upstream_key_encrypted` 仍然必须加密存储（防止数据库泄露），`SAFETYHUB_DATA_KEY` 丢失时允许通过客户端持有的原始 Key 重新录入恢复 |
| F15.1.5-C3 | 一旦 ApiKeyRecord 进入 K-Decoupled 模式，不允许再回退到 K-Sync 模式（避免审计混乱） |
| F15.1.5-C4 | K-Decoupled 模式下，`safetyhub_key` 必须以 `sk-sh-` 前缀标记，便于审计区分 |
| F15.1.5-C5 | 模式切换事件必须写入管理员操作审计 |

#### F15.1.6 — 上游 Key 替换路径（阶段 5 / 6）

> 背景：中转站 Key 旋转、迁移或失效后，必须能在不影响客户端的前提下替换上游 Key。

| 路径 | 适用场景 | 触发方 | 实现阶段 |
|------|---------|-------|---------|
| **路径 A 单条替换** | 单个 ApiKey 的上游 Key 失效或旋转 | 管理员后台 UI | 阶段 5 |
| **路径 B 批量替换 CSV** | 批量更新历史 Key（如导入新中转站 Key 顶替旧的） | 管理员上传 CSV | 阶段 5 |
| **路径 C 自动续约** | 中转站迁移：从一个 Provider 全量迁移到另一个 | 管理员触发 KeyProvider | 阶段 6 |

**路径 A：单条替换流程**

```
1. 管理员后台 → ApiKey 详情 → "替换上游 Key"按钮
2. 弹窗输入：新中转站 Key 明文（或粘贴）
3. 后端：
   a. encrypt(新Key) → upstream_key_encrypted
   b. 同步刷新 upstream_key_prefix / upstream_key_suffix
   c. 标记 is_decoupled = True（如原本是 K-Sync）
   d. 写入 admin_operation_logs：「替换 ApiKey-xxx 的上游 Key」
4. 客户端的 safetyhub_key 不变，下次请求自动使用新 upstream_key
```

**路径 B：CSV 批量替换流程**

```
1. 管理员后台 → ApiKey 列表 → "批量替换上游 Key" → 上传 CSV
2. CSV 格式（两种二选一）：
   方案 A：safetyhub_key_prefix, new_upstream_key
           sk-sh-ab,            sk-newprov-xxx
   方案 B：safetyhub_key_full,  new_upstream_key
           sk-sh-abcdwxyz,      sk-newprov-xxx
3. 后端逐行：
   a. 通过 prefix/full 找到 ApiKeyRecord
   b. encrypt(new_upstream_key) → 替换字段
   c. 更新 provider_name（如果新中转站类型不同）
   d. 标记 is_decoupled = True
   e. 写入 admin_operation_logs
4. 返回结果汇总：成功 N 条 / 失败 M 条（带原因）
```

**路径 C：自动续约流程（阶段 6）**

```
1. 管理员后台 → ApiKey 列表 → "通过新中转站重新创建" → 选择新 Provider
2. 后端遍历所有 ApiKeyRecord：
   a. 调用 new_provider.create_key(KeyCreateParams) 在新中转站创建
   b. 拿到新 upstream_key
   c. encrypt(新Key) → 替换 upstream_key_encrypted
   d. provider_name 切换为新 Provider
   e. 标记 is_decoupled = True
   f. （可选）调用 old_provider.revoke_key() 吊销旧 Key
3. 全程客户端的 safetyhub_key 不变，业务无感切换
```

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F15.1.6-C1 | 替换上游 Key 不得改变 `safetyhub_key_hash`、`id`、`key_prefix`、`key_suffix`，否则违反"客户端无感"原则 |
| F15.1.6-C2 | 替换操作必须写入 `admin_operation_logs`，包含：操作人、新旧 upstream_key 前后缀、provider_name 变化、操作时间 |
| F15.1.6-C3 | 路径 B CSV 上传必须支持事务回滚：单行失败可标记跳过，全文件解析失败不修改任何记录 |
| F15.1.6-C4 | 路径 C 自动续约必须支持中断恢复：已处理的记录不重复创建，失败的记录可重试 |
| F15.1.6-C5 | 替换完成后第一次请求必须验证新 upstream_key 有效性，失败时回滚到旧 Key（除非旧 Key 已显式标记为吊销） |

#### F15.2 — 阶段 6 KeyProvider 抽象层

> 目标：当未来更换中转站（如从 OneAPI 改为自建网关），SafetyHub 核心链路代码（中继、扫描、归档、审计、告警）和管理后台前端代码均**零改动**，只需新增一个 Provider 实现类并修改配置。

**抽象接口（`governance/key_provider.py`）**

```python
class KeyProvider(ABC):
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
```

**Provider 实现矩阵**

| Provider | 适用场景 | 创建能力 | 吊销能力 | 备注 |
|----------|---------|---------|---------|------|
| `passthrough` | 阶段 1~5 默认，不做映射 | 不支持 | 不支持 | 退化到原始透传 |
| `static` | 中转站不开放管理 API，少量 Key 手动配置 | 不支持，仅查询 | 不支持 | Key 配置在 `.env` 或 YAML，绑定时手动选择 |
| `oneapi` | OneAPI/OneHub 系列（如 yxai-api.nanfu.com） | 支持，调用 `/api/token` | 支持 | 需配置 `key_provider_admin_token` |
| `openai_compat` | 兼容 OpenAI Key 管理协议的网关 | 支持 | 支持 | 通过 `/v1/api-keys` 接口 |

**前端无感知原则**

- 前端只调用 SafetyHub 自身的 `/admin/api/api-keys` 接口
- 创建 Key 的请求体在不同 Provider 下保持一致（name / owner_user_id / expires_at / metadata），模型权限、token 额度和资源能力权限在中转站侧配置和生效
- 创建后的响应只返回 SafetyHub Key + 中转站 Key 前后缀，不返回 Provider 类型细节
- 前端不需要知道底层是哪个中转站，也不需要为切换中转站做任何代码改动

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F15.2-C1 | KeyProvider 必须是无状态的，所有持久化通过 SafetyHub 的 `api_keys` 表管理 |
| F15.2-C2 | Provider 调用失败时必须有降级策略：创建失败回滚 SafetyHub Key 记录；查询失败不阻塞主链路 |
| F15.2-C3 | 切换 Provider 时旧 Key 记录保留 `provider_name` 标记，可通过迁移脚本批量重建 |
| F15.2-C4 | 中转站真实 Key 必须加密存储（`upstream_key_encrypted` 字段，使用 `SAFETYHUB_DATA_KEY` 解密），日志和管理后台只展示前后缀 |
| F15.2-C5 | `KeyProvider` 接口签名一旦定型，新增能力（如配额查询）必须通过可选方法或扩展接口加入，不得破坏既有 Provider 实现 |

**验收标准**

- [ ] 阶段 1~3：`upstream_api_key=None` 走透传路径，所有原有测试通过
- [ ] 阶段 3：`api_keys` 表自动创建，Schema 覆盖阶段 5/6 需要字段
- [ ] 阶段 3：`key_provider_type` 配置存在但不影响运行
- [ ] 阶段 5：能在管理后台手动录入历史中转站 Key，默认 K-Sync 使用
- [ ] 阶段 6：能在管理后台通过 Provider 一次性创建 SafetyHub Key 和中转站 Key
- [ ] 阶段 6：在 `oneapi` 和 `static` 之间切换，前端代码和核心链路代码均无改动
- [ ] 阶段 6：吊销 Key 时同时吊销中转站对应 Key，并写入管理员操作审计

---

### F16 — 临时审批放行（Temporary Approval）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F16 |
| **优先级** | P2 — 阶段 9 实现 |
| **描述** | 当请求命中敏感规则但业务确需上传时，向飞书/企微发送审批卡片，审批通过后生成一次性放行令牌 |

**流程**

```
请求命中 warn/可审批 block
  │
  ├─ 创建 ApprovalRequest，状态 pending
  ├─ 推送飞书/企微审批卡片给审批人
  ├─ 客户端收到 pending/blocked 伪装响应或业务系统轮询审批状态
  ├─ 审批通过 → 生成一次性 approval_token，绑定 request_hash/user/model/rule/过期时间
  └─ 用户重试并携带 approval_token → 校验通过后放行并记录审计
```

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F16-C1 | 审批只允许对 `warn` 或配置为 `approvable_block` 的规则触发，高危凭据类规则默认不可审批 |
| F16-C2 | 审批令牌必须一次性使用、短有效期、绑定原始请求哈希，不能泛化为长期白名单 |
| F16-C3 | 审批消息不得包含完整敏感原文，只展示脱敏片段、规则、用户、模型、请求 ID |
| F16-C4 | 审批通过、拒绝、超时、使用都必须写入审计和管理员操作日志 |
| F16-C5 | 阶段 1~8 不默认启用审批，避免阻塞式人工流程影响核心代理稳定性 |

---

### F17 — 文件上传解析、拦截与脱敏（File Security）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F17 |
| **优先级** | P2 — 阶段 10 实现 |
| **描述** | 对上传给大模型的文件进行文本抽取、扫描、拦截、审批或脱敏重写，覆盖常见文档格式 |

**支持范围**

| 文件类型 | 阶段 10 建议 | 说明 |
|----------|-----------|------|
| TXT / Markdown / CSV / JSON | 支持解析与扫描 | 文本直接进入扫描器 |
| PDF | 支持文本型 PDF | 扫描件/OCR 放后续增强 |
| DOCX / XLSX / PPTX | 支持抽取文本 | 先拦截或审批，脱敏重写后置 |
| 图片 / 扫描件 | 后续 OCR | 阶段 10 之前默认不可解析高风险 |
| ZIP / 二进制 | 默认拒绝或审批 | 防止压缩包绕过 |

**处理动作**

| 结果 | 动作 |
|------|------|
| pass | 允许上传并记录文件哈希 |
| warn | 告警、审批或放行，按规则配置决定 |
| block | 拒绝上传并返回伪装响应 |
| unparseable | 默认拒绝或进入人工审批 |
| sanitized | 生成脱敏副本，上传脱敏文件而非原文件 |

**设计结论**

- 文件安全需要做，但不建议混入 v1.0 核心链路实现；先预留入口、字段和 capability
- 真正脱敏文件会涉及格式保真、表格公式、PDF 重写、附件/批注/隐藏 sheet 等复杂问题，应作为 v1.2 独立能力实现
- 对 OpenAI Files、Responses、Assistants 或多模态上传入口，需要按 endpoint 做协议适配，不能只扫描 chat messages

---

### F18 — Key 级安全策略（Per-Key Security Policy）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F18 |
| **优先级** | P1 — v1.0 仅预留 schema，v1.2 实现 |
| **描述** | 允许为每个 APIKey、用户或部门绑定独立的安全策略，在共享同一套规则库的前提下做差异化决策（启用/禁用/级别替换/阈值调整） |

**典型场景**

| 场景 | 策略示例 |
|------|----------|
| CEO / 法务 Key | 所有 warn 规则降级为 pass，所有 block 规则降级为 warn 但不拦截 |
| 实习生 Key | 严格策略，所有 warn 规则升级为 block |
| 研发部门 Key | 放行 `KW-007 源代码泄露` 的关键词，保留 PII 拦截 |
| 客服部门 Key | 严格 PII 拦截，关闭商业机密相关规则（不会接触） |
| 调试 / 灰度 Key | 全部规则强制 warn，便于观察命中而不影响业务 |

**数据模型（v1.2 实现）**

| 表 | 字段 | 说明 |
|----|------|------|
| `security_policies` | `id`、`name`、`description`、`rule_overrides`（JSON）、`block_threshold`、`warn_to_block_keywords`、`inherit_from`、`is_default` | 策略主表 |
| `api_keys` | `security_policy_id`（v1.0 预留 NULL） | 关联策略 |

**`rule_overrides` JSON 示例**

```json
{
  "KW-001": "disabled",
  "KW-007": "pass",
  "RG-003": "warn",
  "RG-004": "block"
}
```

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F18-C1 | 策略覆盖必须基于全局规则的"diff"，不允许在策略内定义全新规则，避免规则碎片化 |
| F18-C2 | 策略加载结果必须缓存，单次扫描不得为同一策略重复编译规则 |
| F18-C3 | 策略未指定时退化为全局规则，行为与 v1.0/v1.1 完全一致 |
| F18-C4 | 策略修改必须写入管理员操作审计；老审计记录字段允许 NULL，不强制回填 |
| F18-C5 | 策略支持继承（`inherit_from`），最多继承 3 级，避免循环依赖 |
| F18-C6 | 高危规则（凭据/私钥/绝密标识）必须在策略中标记为"不可降级"，避免被滥用绕过 |

**v1.0 预留要求**

| 预留点 | 文件 | 说明 |
|--------|------|------|
| `security_policies` 表 | `storage/models.py` | 仅建表，不写入 |
| `api_keys.security_policy_id` 字段 | `storage/models.py` | 默认 NULL，建表时一并创建 |
| `audit_logs.security_policy_id` 字段 | `storage/models.py` | 默认 NULL，老记录免回填 |
| `message_archives.security_policy_id` 字段 | `storage/models.py` | 默认 NULL |
| `engine/scanner.py` 接口签名 | 文档说明 | v1.2 改为 `scan(text, policy=None)`，默认 None 走全局规则 |

**验收标准**

- [ ] v1.0：4 个表/字段建立，不影响任何路径，全部已有测试通过
- [ ] v1.2：可在管理后台为单个 APIKey 绑定策略
- [ ] v1.2：绑定策略后扫描行为按 `rule_overrides` 差异化决策
- [ ] v1.2：不绑定策略的 Key 与原全局规则行为完全一致
- [ ] v1.2：策略修改写入管理员操作审计，归档与审计可查询"此请求使用了哪个策略"

---

### F19 — 审批链路由（Approval Chain Routing）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F19 |
| **优先级** | P2 — v1.0 仅预留 schema，v1.2 与 F16 一同实现 |
| **描述** | 在 F16 临时审批的基础上，根据 APIKey 所属用户/部门/规则级别等维度路由到不同审批人，并支持超时升级 |

**典型场景**

| 触发条件 | 审批链 |
|---------|--------|
| 张三（研发部）命中 warn | 一级：研发组长（30 分钟超时） → 二级：研发总监（60 分钟超时） |
| 李四（财务部）命中 block 但允许审批 | 一级：财务总监（直接，无升级） |
| 跨部门请求或 CFO 级别 Key | 一级：信息安全负责人（无升级） |
| 高危凭据规则 | 不可审批，直接 block |

**数据模型（v1.2 实现）**

| 表 | 字段 | 说明 |
|----|------|------|
| `approval_chains` | `id`、`name`、`chain_definition`（JSON）、`trigger_rule_levels`、`trigger_capabilities`、`escalation_policy` | 审批链定义 |
| `api_keys` | `approval_chain_id`（v1.0 预留 NULL） | 关联审批链 |
| `approval_requests` | `chain_id`、`current_level`、`escalated_at`（v1.0 预留） | 关联到具体审批链与执行进度 |

**`chain_definition` JSON 示例**

```json
[
  {
    "level": 1,
    "approver_type": "user",
    "approver_id": "manager_id",
    "timeout_minutes": 30,
    "on_timeout": "escalate"
  },
  {
    "level": 2,
    "approver_type": "role",
    "approver_id": "security_admin",
    "timeout_minutes": 60,
    "on_timeout": "auto_reject"
  }
]
```

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F19-C1 | 审批链必须支持组织维度路由（用户、部门、角色），不允许硬编码审批人 |
| F19-C2 | 审批链最多支持 5 级，避免无限升级 |
| F19-C3 | 超时策略必须明确：`escalate`（升级到下一级）、`auto_reject`（自动拒绝）、`auto_approve`（仅低风险规则允许） |
| F19-C4 | 审批通过的令牌必须保持 F16 约束：一次性、短有效期、绑定请求哈希 |
| F19-C5 | 升级或超时事件必须独立写入审计，便于追溯审批延迟根因 |
| F19-C6 | 高危规则（凭据/私钥）即使绑定了审批链也不可触发审批，必须直接 block |

**v1.0 预留要求**

| 预留点 | 文件 | 说明 |
|--------|------|------|
| `approval_chains` 表 | `storage/models.py` | 仅建表，不写入 |
| `api_keys.approval_chain_id` 字段 | `storage/models.py` | 默认 NULL |
| `approval_requests.chain_id` / `current_level` / `escalated_at` | `storage/models.py` | 默认 NULL，建表时一并创建 |

**验收标准**

- [ ] v1.0：3 个表/字段建立，与 v1.0 行为完全无关
- [ ] v1.2：可在管理后台创建多级审批链，并绑定到 APIKey
- [ ] v1.2：触发审批时按链路推送给当前级别审批人
- [ ] v1.2：超时按 `on_timeout` 策略升级或自动拒绝
- [ ] v1.2：高危规则不可触发审批，直接 block
- [ ] v1.2：所有升级、超时、决策事件写入审计

---

### F20 — 中转站配额与速率限制观测（Upstream Quota Visibility）

| 项目 | 说明 |
|------|------|
| **功能 ID** | F20 |
| **优先级** | P1 — v1.0 仅预留 schema，v1.1+ 可与 KeyProvider 一同接入中转站观测能力 |
| **描述** | SafetyHub 不作为模型/token/资源权限的权威系统，不在本地默认执行配额或速率限制拦截；如中转站提供查询接口，SafetyHub 可同步展示配额、速率限制和用量快照，用于审计、告警和运营观测 |

**观测维度**

| 维度 | 示例 |
|------|------|
| 总配额快照 | 中转站返回该 Key 累计 token 上限和已用量 |
| 模型配额快照 | 中转站返回 `gpt-4o` / `deepseek-r1` 等模型额度和用量 |
| 能力配额快照 | 中转站返回 `function_call`、`file_upload` 等资源能力额度和用量 |
| 速率限制快照 | 中转站返回 QPS、TPM、RPM、并发数等限制配置 |

**数据模型**

| 数据 | 归属 | SafetyHub 行为 |
|------|------|----------------|
| 模型配额 | 中转站 | 不在 `api_keys` 表建字段；如中转站提供查询接口，阶段 6+ 可通过 Provider 实时读取或短期缓存展示 |
| 能力配额 | 中转站 | 不在 `api_keys` 表建字段；SafetyHub 不本地判定 function_call/file_upload 等资源额度 |
| 速率限制 | 中转站 | 不在 `api_keys` 表建字段；超限响应由中转站返回并由 SafetyHub 透传或归档 |
| 用量快照 | 中转站 | 如需观测，可建立独立观测表或指标，不污染 APIKey 映射表 |

**行为约束**

| 约束 ID | 约束内容 |
|---------|---------|
| F20-C1 | SafetyHub 默认不在 relay 边界执行模型/token/资源权限配额拦截 |
| F20-C2 | 中转站返回的 401/403/429 等权限或配额响应应被 SafetyHub 清晰透传或按兼容错误响应返回 |
| F20-C3 | SafetyHub 可记录 request_id、api_key_id、状态码、上游错误类型用于审计和告警，但不得把自身变成第二套资源权限系统 |
| F20-C4 | 如未来需要本地安全限流，应作为 SafetyHub 安全防护能力单独设计，不复用中转站资源配额语义 |

**v1.0 预留要求**

| 预留点 | 文件 | 说明 |
|--------|------|------|
| Provider 查询接口预留 | `governance/key_provider.py` | 阶段 6 可定义可选 quota/status 查询方法，但不要求所有 Provider 实现 |
| 管理后台展示位 | `admin/static/api_keys.html` | 显示“资源权限由中转站管理”，后续可增加跳转中转站控制台链接 |

**验收标准**

- [x] v1.0：`api_keys` 表不包含模型配额、能力配额、速率限制和用量快照字段
- [ ] v1.1+：如 Provider 支持查询，可在管理后台只读展示中转站配额/速率限制状态
- [ ] v1.1+：中转站返回 401/403/429 时 SafetyHub 不吞错、不改写为本地权限错误

---

## 五、功能优先级与阶段映射

| 功能 | ID | 优先级 | 阶段 |
|------|----|--------|------|
| 中继转发 | F1 | P0 | 阶段 1 |
| 伪装回复 | F2 | P0 | 阶段 2 |
| 消息归档 | F3 | P0 | 阶段 3 |
| 关键词规则检测 | F4 | P0 | 阶段 2 弱规则 / 阶段 7 完整规则 |
| 正则规则检测 | F5 | P0 | 阶段 2 手机号 / 阶段 7 完整 PII |
| 扫描器调度引擎 | F6 | P0 | 阶段 2 |
| 审计追溯 | F7 | P1 | 阶段 3 |
| 管理后台 | F8 | P1 | 阶段 4 |
| 告警通知 | F9 | P1 | 阶段 8 |
| NER 命名实体识别 | F10 | P2 | 阶段 10 |
| 全文搜索 | F11 | P2 | 阶段 10 |
| 统计面板增强 | F12 | P2 | 阶段 8 |
| 对话回放 | F13 | P2 | 阶段 10 |
| 基础治理与运行基线 | F14 | P0 | 阶段 1 |
| APIKey 映射、安全策略与多上游路由 | F15 | P1 | 阶段 3 预留 / 阶段 5 APIKey / 阶段 6 Provider |
| 临时审批放行 | F16 | P2 | 阶段 9 |
| 文件上传解析、拦截与脱敏 | F17 | P2 | 阶段 10 |

---

## 六、功能间依赖关系

```
F14 基础治理 ──→ F1 中继转发 ─────────────────────────→ 核心基座
    │               │
    │               ├── F6 扫描器调度引擎 ──→ F4 关键词规则 ──→ F7 审计追溯 ──→ F9 告警通知
    │               │                     └─→ F5 正则规则  ──↗
    │               │
    │               ├── F2 伪装回复 ──→ (依赖 F6 的拦截决策)
    │               │
    │               ├── F3 消息归档 ──→ F8 管理后台
    │               │
    │               └── F15 权限预留 ──→ F16 临时审批 ──→ F17 文件安全
    │
    └── RequestContext / Header Policy / Metrics / Retention
```

**关键依赖链**：F14 → F1 → F6 → F4/F5 → F2（这是最小可用路径，优先实现）。F15 必须在数据结构和接口字段上预留，但完整权限决策可后置。

---

## 七、非功能需求

| 维度 | 指标 | 目标 |
|------|------|------|
| 性能 | 中继转发额外延迟 | < 50ms（非流式） |
| 性能 | 安全检测耗时 | < 10ms/请求 |
| 性能 | 并发 SSE 连接 | ≥ 50 |
| 可用性 | 服务可用率 | ≥ 99.5% |
| 可靠性 | 检测遗漏率 | ≤ 1%（关键词/正则覆盖范围内） |
| 可靠性 | 误报率 | ≤ 5% |
| 安全性 | 管理后台访问控制 | Basic Auth + IP 白名单 |
| 安全性 | 日志脱敏 | 原始敏感文本不进入日志 |
| 安全性 | APIKey 存储 | 只存哈希与前后缀，禁止明文入库 |
| 安全性 | 文件上传 | 默认限制大小和类型，不可解析文件按高风险处理 |
| 可观测性 | Request ID 覆盖率 | 100% 请求、日志、审计、告警可关联 |
| 可观测性 | 健康检查 | live/ready 分离，ready 覆盖数据库和规则加载 |
| 数据治理 | 归档保留 | 默认 180 天，可配置清理策略 |
| 数据治理 | 审计保留 | 默认 365 天，管理员操作审计不可静默删除 |
| 可维护性 | 规则热加载 | 修改后 5s 生效 |
| 可维护性 | 部署方式 | `docker compose up -d` 一键启动 |
