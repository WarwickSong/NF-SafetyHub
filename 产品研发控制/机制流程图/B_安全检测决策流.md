# B. 安全检测与处置决策流（block / desensitize / pass）

> 视角：Chat Completions 请求进入 Scanner 后，如何决定拦截伪装、脱敏改写或透明透传。
> 对应代码：`engine/scanner.py`、`engine/normalizer.py`、`engine/rules_keyword.py`、`engine/rules_regex.py`、`engine/models.py`、`proxy/relay.py`、`proxy/fake_response.py`。

```mermaid
flowchart TD
    Start(["/v1/chat/completions 进入 Relay"])
    Start --> CheckPath{"path == /v1/chat/completions ?"}
    CheckPath -- "否<br/>(embeddings/images/responses/未知)" --> Passthrough["默认透明透传<br/>不进入扫描"]

    CheckPath -- "是" --> Extract["extract_latest_text_from_request<br/>取最新允许 role 的文本消息"]
    Extract --> HasText{"文本非空 ?"}
    HasText -- "否" --> Passthrough
    HasText -- "是" --> Norm["TextNormalizer.normalize<br/>Unicode NFKC / 大小写 / 全半角统一"]

    Norm --> Orch["ScannerOrchestrator.scan<br/>遍历注册扫描器"]
    Orch --> KW["KeywordScanner<br/>YAML 关键词表 + AC 自动机"]
    KW --> KWHit{"任一 result.blocked ?"}
    KWHit -- "是" --> Aggregate["AggregatedScanResult<br/>block_result 记录命中规则"]
    KWHit -- "否" --> RX["RegexScanner<br/>YAML 正则表 + 预编译"]
    RX --> Aggregate

    Aggregate --> Level{"判定结论<br/>(aggregated.blocked / action)"}

    %% ============ 分支 1: BLOCK ============
    Level -- "blocked = True" --> B1["选择 block_result<br/>读取命中规则 ID / level"]
    B1 --> B2["generate_fake_response<br/>模板: 抱歉，您输入的内容...<br/>model 字段沿用请求"]
    B2 --> B3{"is_stream ?"}
    B3 -- "是" --> B4["StreamingResponse<br/>逐 2 字符 chunk + [DONE]"]
    B3 -- "否" --> B5["JSONResponse<br/>OpenAI chat.completion 格式"]
    B4 --> BAudit
    B5 --> BAudit
    BAudit["_write_chat_audit<br/>action='blocked' + rule_id 入审计"]
    BAudit --> BArchive["_write_chat_archive<br/>原始 prompt + 伪装 response 入归档"]
    BArchive --> ReturnFake(["返回伪装响应<br/>不触达上游"])

    %% ============ 分支 2: DESENSITIZE ============
    Level -- "未 block 但命中脱敏规则" --> D1["desensitize_chat_request_body<br/>按 role/字段定向改写 messages<br/>例: 手机号 → 138****1234"]
    D1 --> D2["was_desensitized = (body != original_body)"]
    D2 --> D3["_select_relay_payload<br/>用脱敏后 dict 重序列化<br/>(不再透传 raw_body)"]
    D3 --> DAudit["_write_chat_audit<br/>action='desensitized'"]
    DAudit --> Forward(["转发上游<br/>上游只看到脱敏文本"])

    %% ============ 分支 3: PASS / WARN ============
    Level -- "pass / warn 未命中阻断" --> P1["保留原 body + raw_body"]
    P1 --> P2["_select_relay_payload<br/>优先字节级透传 raw_body"]
    P2 --> PAudit{"warn 命中 ?"}
    PAudit -- "是" --> PWarnAudit["_write_chat_audit<br/>action='warn' (记录但不拦截)"]
    PAudit -- "否" --> NoAudit["不写审计"]
    PWarnAudit --> Forward
    NoAudit --> Forward
    Passthrough --> Forward

    Forward --> Upstream["上游中转站<br/>(真实大模型回复)"]
    Upstream --> RespArchive["响应回流<br/>_write_chat_archive 异步入队<br/>(流式: StreamArchiveCollector 拼接)"]
    RespArchive --> ReturnReal(["返回真实响应给客户端"])

    classDef block fill:#fde2e2,stroke:#c0392b,color:#000
    classDef desens fill:#fff3cd,stroke:#b7791f,color:#000
    classDef pass fill:#dff0d8,stroke:#27ae60,color:#000
    class B1,B2,B3,B4,B5,BAudit,BArchive,ReturnFake block
    class D1,D2,D3,DAudit desens
    class P1,P2,NoAudit,PWarnAudit,Passthrough,ReturnReal pass
```

## 决策口径（与 `_action_from_scan_result` 一致）

| 输入 | 输出 action | 是否触达上游 | 是否写审计 |
|------|-------------|--------------|------------|
| `scan_result.blocked == True` | `blocked` | 否（伪装回复） | 是 |
| 未 block 但 body 被改写 | `desensitized` | 是（发送脱敏后文本） | 是 |
| 未命中或 warn | `passed` / `warn` | 是（字节级透传 raw_body） | warn 写，pass 不写 |
| 非 Chat 接口 / 文本为空 | `passed` | 是 | 否 |

## 关键约束（与代码一致）

- **F2-C1**：伪装回复完全兼容当前请求的 OpenAI 响应格式（含流式 chunk 形态）。
- **F2-C2**：伪装内容不泄露具体规则名与命中片段。
- **F2-C4**：伪装回复的 `model` 字段沿用用户请求的 `model`。
- **F1-C11**：仅 Chat Completions 必走 Scanner，其他 `/v1/*` 默认透传。
- **优先级**：关键词命中 block 后直接短路，不再跑后续正则扫描器（`ScannerOrchestrator.scan` 中 `if any(blocked): return`）。
