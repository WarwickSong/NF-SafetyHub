# D. APIKey 治理与上游 Key 替换流（K-Sync 机制）

> 视角：用户拿到的 SafetyHub Key 与最终打到中转站的 Key 不是同一个，这套替换、加密、轮转、吊销是怎么做的。
> 对应代码：`governance/api_keys.py`、`governance/key_provider.py`、`governance/providers/*.py`、`middleware/identity.py`、`proxy/relay.py`。

```mermaid
flowchart TD
    %% ==================== 上：管理员创建 Key ====================
    subgraph Create["① 管理员创建 / 同步 APIKey"]
        direction TB
        Admin["管理员后台<br/>POST /admin/api/api-keys"]
        Admin --> Mode{"create_mode ?"}
        Mode -- "manual<br/>(粘贴上游 Key)" --> ManualKey["直接使用 payload.upstream_key"]
        Mode -- "provider<br/>(K-Sync 同步)" --> CallProvider["KeyProvider.create_key(params)"]

        CallProvider --> Provider{"KEY_PROVIDER_TYPE"}
        Provider -- "passthrough" --> P1["PassthroughKeyProvider<br/>(占位, 不真正创建)"]
        Provider -- "static" --> P2["StaticKeyProvider<br/>从配置取固定 key"]
        Provider -- "oneapi_nanfu_yxai" --> P3["OneApiNanfuYxaiKeyProvider<br/>调中转站 API 创建用户 Key<br/>返回 UpstreamKeyInfo"]

        P1 --> UpstreamSecret
        P2 --> UpstreamSecret
        P3 --> UpstreamSecret
        ManualKey --> UpstreamSecret
        UpstreamSecret["拿到真实上游 Key 明文<br/>upstream_info.key_secret"]

        UpstreamSecret --> Encrypt["ApiKeyCrypto.encrypt<br/>Fernet AES-128-CBC + HMAC<br/>密钥 = SAFETYHUB_DATA_KEY<br/>密文格式: v2:gAAAA..."]

        Encrypt --> Reuse{"reuse_upstream_key ?"}
        Reuse -- "是 (K-Sync 默认)" --> KSync["SafetyHub Key == 上游 Key<br/>(用户直接用上游 Key 调 SafetyHub)"]
        Reuse -- "否 (独立颁发)" --> NewKey["secrets.token_urlsafe<br/>生成新的 sk-safetyhub-*<br/>仅 SafetyHub 内可识别"]

        KSync --> Record
        NewKey --> Record
        Record["ApiKeyRecord 入库<br/>id / key_prefix / key_suffix<br/>encrypted_safetyhub_key<br/>encrypted_upstream_key<br/>owner_user_id / department / cost_center<br/>provider_name / expires_at"]
        Record --> DB[("PostgreSQL<br/>api_keys")]
        Record --> Return["返回给管理员一次性明文<br/>(后续仅可 reveal)"]
    end

    %% ==================== 下：运行时使用 ====================
    subgraph Use["② 用户请求时的 Key 替换"]
        direction TB
        ClientReq["用户客户端<br/>Authorization: Bearer &lt;SafetyHub Key&gt;"]
        ClientReq --> Middleware["ApiKeyIdentityMiddleware.dispatch"]

        Middleware --> CountCheck{"api_key_count == 0 ?"}
        CountCheck -- "是 且 ALLOW_EMPTY_API_KEYS_PASSTHROUGH" --> EmptyIdentity["RequestIdentity()<br/>(历史透传, 生产禁用)"]
        CountCheck -- "是 且 生产关闭透传" --> Reject401a["401 api key is required"]
        CountCheck -- "否" --> ExtractBearer["_extract_bearer_key<br/>(支持 5s 短缓存避免雪崩)"]

        ExtractBearer --> FindKey["ApiKeyService.find_by_raw_key<br/>用 raw_key 哈希查表"]
        FindKey --> Found{"找到 + is_record_active ?"}
        Found -- "否" --> Reject401b["401 invalid api key"]
        Found -- "是" --> Decrypt["ApiKeyCrypto.decrypt<br/>读 encrypted_upstream_key<br/>→ 真实上游 Key 明文"]
        Decrypt --> BuildIdentity["RequestIdentity:<br/>- api_key_id<br/>- user_id<br/>- upstream_api_key (明文)<br/>- key_prefix"]
        BuildIdentity --> StashState["request.state.identity"]

        StashState --> RelayHandler["proxy.relay 处理"]
        RelayHandler --> BuildHeaders["build_upstream_headers<br/>注入 Authorization: Bearer &lt;真实上游 Key&gt;<br/>剥离客户端原始 Authorization"]
        BuildHeaders --> Forward["转发到中转站"]
    end

    %% ==================== 关联线 ====================
    DB -.->|"运行时查询"| FindKey
    Encrypt -.->|"同一对 Fernet"| Decrypt

    %% ==================== 其他治理操作 ====================
    subgraph Ops["③ 其他治理操作"]
        direction LR
        Reveal["POST /api-keys/{id}/reveal<br/>解密返回明文<br/>(写 admin_operations)"]
        Replace["POST /api-keys/{id}/replace<br/>替换 upstream_key<br/>重新加密入库"]
        Bulk["POST /api-keys/bulk-replace<br/>CSV 批量替换"]
        Revoke["DELETE /api-keys/{id}<br/>本地标记 revoked<br/>+ KeyProvider.revoke_key (中转站同步吊销)"]
    end
    Reveal --> DB
    Replace --> DB
    Bulk --> DB
    Revoke --> DB
    Revoke -.-> P3

    classDef secret fill:#fde2e2,stroke:#c0392b,color:#000
    classDef crypto fill:#fff3cd,stroke:#b7791f,color:#000
    classDef db fill:#e8f5e9,stroke:#2e7d32,color:#000
    class UpstreamSecret,Decrypt secret
    class Encrypt crypto
    class DB db
```

## 关键约束（与代码一致）

- **永不明文落库**：`encrypted_upstream_key` 与 `encrypted_safetyhub_key` 均用 Fernet 加密，密文带 `v2:` 版本前缀，便于后续算法升级。
- **数据密钥来源**：`SAFETYHUB_DATA_KEY` 环境变量；生产启动时 `validate_startup_settings` 强校验非空。
- **K-Sync 默认**：`reuse_upstream_key=True` 时 SafetyHub Key 直接等于上游 Key，对用户无感切换；`False` 时颁发独立 `sk-safetyhub-*`。
- **运行时性能**：Identity 中间件维护 `api_key_count` 短缓存（默认 5s），避免每次请求都打 DB 计数。
- **明文流向单向**：上游 Key 明文只在「创建/replace 接收 → 加密落库」与「中间件读取 → 立即注入 Authorization → 转发上游」两个瞬间存在，不会出现在日志、归档、审计中。
- **吊销同步**：`DELETE` 既本地标记 revoked，也调用 `KeyProvider.revoke_key` 通知中转站，避免外部 Key 残留。
