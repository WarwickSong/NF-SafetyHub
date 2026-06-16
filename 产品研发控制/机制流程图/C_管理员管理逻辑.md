# C. 管理员管理逻辑（后台全景）

> 视角：管理员从浏览器登录到操作各功能模块的完整链路。
> 对应代码：`admin/router.py`、`admin/static/*.html`、`middleware/auth.py`、`storage/admin_ops.py`、`storage/archive.py`、`storage/audit.py`、`engine/rules_config.yaml`。

```mermaid
flowchart TD
    Browser["管理员浏览器<br/>(内网访问 http://llm-safetyhub.nanfu.com/admin/)"]
    Browser --> Nginx2["内网 Nginx<br/>location /admin/ → safetyhub:8000"]

    Nginx2 --> StaticMW["AdminStaticAuthMiddleware<br/>(仅拦截 /admin 静态页, 放行 /admin/api/*)"]

    StaticMW --> StaticCheck{"路径在公开白名单 ?<br/>/admin/login.html<br/>/admin/css/style.css<br/>/admin/js/app.js"}
    StaticCheck -- "是" --> LoginPage["返回 login.html<br/>(静态页 + app.js)"]
    StaticCheck -- "否" --> IPCheck{"admin_ip_whitelist 命中 ?"}
    IPCheck -- "否" --> Forbidden["403 Admin access denied"]
    IPCheck -- "是" --> SessionCheck{"safetyhub_admin_session<br/>cookie HMAC 校验 ?"}
    SessionCheck -- "无效/过期" --> Redirect["302 → /admin/login.html?next=..."]
    SessionCheck -- "有效" --> StaticPage["返回对应 HTML 页面<br/>(index/archives/audits/...)"]

    LoginPage --> LoginPost["POST /admin/api/login<br/>{username, password}"]
    LoginPost --> ValidateLogin{"validate_admin_login<br/>secrets.compare_digest"}
    ValidateLogin -- "失败" --> Unauthorized["401 Invalid admin credentials"]
    ValidateLogin -- "成功" --> SetCookie["set_admin_session_cookie<br/>HMAC(payload, ADMIN_PASSWORD)<br/>HttpOnly + SameSite=Lax<br/>max_age=8h"]
    SetCookie --> Redirect2["前端跳转回 next 路径"]
    Redirect2 --> StaticPage

    StaticPage --> AdminAPI["调用 /admin/api/*<br/>(全部走 require_admin_access 依赖)"]

    AdminAPI --> Modules{"管理后台 8 大模块"}

    %% ===== 仪表盘 =====
    Modules --> Stats["1. 仪表盘<br/>GET /admin/api/stats"]
    Stats --> StatsCache["AdminStatsCache.get_or_set<br/>短缓存 (ADMIN_STATS_CACHE_SECONDS)"]
    StatsCache --> DBStats[("PostgreSQL<br/>archive + audit 聚合<br/>+ 7 日趋势")]

    %% ===== 运行状态 =====
    Modules --> Runtime["2. 运行状态<br/>GET /admin/api/runtime"]
    Runtime --> Snapshot["快照拼装<br/>get_v1_concurrency_snapshot<br/>archive_queue.snapshot()<br/>upstream pool 配置<br/>disk space"]

    %% ===== 消息归档 =====
    Modules --> Archives["3. 消息归档<br/>GET /admin/api/archives?<br/>user/model/action/keyword/时间窗"]
    Archives --> ArchiveReader["ArchiveReader.list / get / stats"]
    ArchiveReader --> DBArch[("PostgreSQL<br/>message_archive")]

    %% ===== 图片资产 =====
    Modules --> Images["4. 图片资产<br/>GET /admin/api/image-assets"]
    Images --> ImageReader["ImageAssetReader<br/>本地文件路径 + sha256 + 状态"]

    %% ===== 审计追溯 =====
    Modules --> Audits["5. 审计追溯<br/>GET /admin/api/audits"]
    Audits --> AuditReader["AuditReader.list / get<br/>按 rule_id/level/scanner_type 过滤"]
    AuditReader --> DBAudit[("PostgreSQL<br/>audit_log")]

    %% ===== 观测 =====
    Modules --> Obs["6. 观测<br/>GET /admin/api/observations/recent"]
    Obs --> ArchiveReader

    %% ===== 规则管理 =====
    Modules --> Rules["7. 规则管理<br/>GET /admin/api/rules<br/>PATCH /admin/api/rules/{id}<br/>POST /admin/api/rules/reload"]
    Rules --> RulesFile["读写 engine/rules_config.yaml<br/>启用/禁用规则"]
    RulesFile --> ReloadScanners["app.state.scanner.reload_all()<br/>热加载关键词 + 正则"]
    ReloadScanners --> ScanRuntime[("内存中的<br/>KeywordScanner / RegexScanner")]

    %% ===== APIKey 治理 =====
    Modules --> Keys["8. APIKey 治理<br/>GET/POST/PATCH/DELETE /admin/api/api-keys<br/>POST /api-keys/{id}/replace<br/>POST /api-keys/{id}/reveal<br/>POST /api-keys/bulk-replace (CSV)"]
    Keys --> KeyService["ApiKeyService<br/>(Fernet 加密 / 校验 / 吊销)"]
    KeyService --> KeyProvider["KeyProvider<br/>(passthrough / static / oneapi_nanfu_yxai)"]
    KeyProvider --> DBKeys[("PostgreSQL<br/>api_key_record (密文)")]

    %% ===== 操作留痕 =====
    Stats --> OpsLog
    Runtime --> OpsLog
    Archives --> OpsLog
    Images --> OpsLog
    Audits --> OpsLog
    Rules --> OpsLog
    Keys --> OpsLog
    OpsLog["_write_admin_operation<br/>记录 admin 用户 + 操作 + 资源"]
    OpsLog --> DBOps[("PostgreSQL<br/>admin_operation")]

    Modules --> OpsView["9. 操作留痕查看<br/>GET /admin/api/admin-ops"]
    OpsView --> DBOps

    classDef auth fill:#e3f2fd,stroke:#1976d2,color:#000
    classDef api fill:#fff3cd,stroke:#b7791f,color:#000
    classDef db fill:#e8f5e9,stroke:#2e7d32,color:#000
    class StaticMW,IPCheck,SessionCheck,ValidateLogin,SetCookie,Redirect,Redirect2,Unauthorized,Forbidden,LoginPage,LoginPost auth
    class Stats,Runtime,Archives,Images,Audits,Obs,Rules,Keys,OpsView,OpsLog api
    class DBStats,DBArch,DBAudit,DBOps,DBKeys,ScanRuntime,RulesFile db
```

## 关键约束（与代码一致）

- **登录态**：`safetyhub_admin_session` cookie = `username:issued_at:HMAC-SHA256(payload, ADMIN_PASSWORD)`，最长 8h，HttpOnly，生产环境强制 Secure（`active_settings.is_production`）。
- **双通道认证**：cookie 失效时也可走 HTTP Basic（`WWW-Authenticate: Basic`），便于脚本/curl 访问。
- **IP 白名单**：`ADMIN_IP_WHITELIST` 非空时强制校验，支持精确 IP 与 CIDR 网段。
- **/admin/api/* 全量受护**：`router = APIRouter(dependencies=[Depends(require_admin_access)])`，仅 `/login` 和 `/logout` 例外。
- **操作留痕**：除查询类只读接口外，所有写操作经 `_write_admin_operation` 落 `admin_operation` 表。
- **stats 短缓存**：避免高频刷新仪表盘时打爆 PostgreSQL。
