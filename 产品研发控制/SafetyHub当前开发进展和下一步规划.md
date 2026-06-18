# LLM-SafetyHub 当前开发进展和下一步规划

> 更新时间：2026-06-18
> 当前阶段：阶段 6A — 单实例 Docker 生产稳定性、高并发治理与数据治理交付
> 当前状态：阶段 1~6A 核心能力已全部落地（详见第二、三、四章）；2026-06 已完成透明中继兼容性修复、训练数据沉淀、数据治理后台、覆盖分析、手动清理和内网 Docker 离线部署数据库保留策略。覆盖分析采用按 `user_id + api_key_id` 分组的确定性 JSON 前缀比较，寻找每组最长有效轨迹集合；不按模型隔离，不使用 lookback，不引入前缀 hash/派生表/外部通信。内网升级部署保留已有 `api_keys` 表，不从 JSON/SQL 重新导入 APIKey，其余当前系统表可按最新模型删除并重建。历史自动化测试基线为 `94 passed`，当前生产代码已继续演进，测试结果需以当前环境复跑为准；最近专项验证包含数据治理覆盖分析测试、离线包 checksum、Compose 配置和当前服务 `/health/ready`。阶段 7 及之后暂不开发，仅保留长期规划；生产上线前重点转为真实上游联调、高并发阶梯压测、PostgreSQL 稳定性、备份恢复、运维安全配置和生产验收。

---

## 一、实际代码状态

本状态基于当前仓库代码检查与自动化测试结果。当前代码已经具备 FastAPI 应用入口、生产启动配置校验、健康检查、Request ID、请求体大小限制、OpenAI-compatible `/v1/*` 通用中继转发、Header 安全透传、单上游路由、共享上游 `httpx.AsyncClient` 连接池、Scanner 调度、关键词/正则扫描、block 拦截伪装回复、请求侧手机号脱敏改写转发、SSE 透传与完整流式归档、规则定时热加载、管理后台规则启停和手动热加载、管理 API 和静态页面 Basic Auth + IP 白名单、Chat 归档/审计写入、正式归档/审计分页筛选和详情 API、统计概览 API、管理员操作审计、最小静态后台、文生图元数据归档、文生图图片本体异步归档、图片资产状态 API、最近对话观测 API、SQLite 旧表缺列补齐、PostgreSQL 运行配置、SQLite 到 PostgreSQL 迁移/验证脚本、R1~R9 schema 预留和 timezone-aware UTC 时间字段。

阶段 5 已实现 `governance/api_keys.py`、`middleware/identity.py`、后台 APIKey CRUD 接口和 `admin/static/api_keys.html` 可操作页面。SafetyHub 支持管理员手动录入已有中转站 Key，默认以 K-Sync 模式保存；数据库保存哈希、前后缀、加密后的上游 Key 和加密后的 SafetyHub Key，不在列表接口默认返回 Key 明文。启用 APIKey 后，`/v1/*` 请求会按客户端 Authorization 查询 `api_keys`，校验本地记录是否存在、active/revoked/expired 状态是否有效，并用解密后的上游 Key 替换转发到中转站的 Authorization。模型权限、token 额度、速率限制和资源能力权限由中转站负责，SafetyHub 不做模型/能力 allowlist 拦截，相关字段已从当前 schema、后台表单和 API 响应中删除。若数据库中还没有任何 APIKey，`/v1/*` 会保持阶段 1-4 的过渡透传行为，便于上线迁移。

阶段 6 已实现 `governance/key_provider.py`、`governance/providers/{passthrough,static_key,oneapi_nanfu_yxai}.py`，`main.py` lifespan 会根据 `KEY_PROVIDER_TYPE` 实例化 Provider 并注入 `ApiKeyService`。后台创建表单支持“手动录入中转站 Key”和“由 KeyProvider 创建”，Provider 创建默认 K-Sync，创建成功后返回完整 SafetyHub Key 供管理员复制；列表默认只展示前后缀，管理员可按需点击 reveal/复制完整 Key 并写入操作审计。`oneapi_nanfu_yxai` 已对接 yxai 中转站登录、创建、获取完整 Key、删除和分页列表接口，支持 `KEY_PROVIDER_BASE_URL`、`KEY_PROVIDER_USERNAME`、`KEY_PROVIDER_PASSWORD_ENV`、`KEY_PROVIDER_AUTH_VERSION`、默认 quota 和重试参数配置。`scripts/import_yxai_keys.py` 已支持从 `yxai_token_export.json` 幂等导入历史中转站 Key。

阶段 6A 当前代码已新增 `middleware/concurrency_limit.py`、`middleware/request_limit.py`、`runtime/upstream_client.py`、`runtime/archive_queue.py`、`runtime/admin_cache.py` 和 `/admin/api/runtime`。`/v1/*` 请求统一进入进程内有界并发队列，代码默认每 worker `V1_MAX_INFLIGHT=150`、`V1_MAX_QUEUE_SIZE=200`；生产环境推荐通过 `.env` 调到每 worker `V1_MAX_INFLIGHT=250`、`V1_MAX_QUEUE_SIZE=500`，4 worker 下容器总目标为 `1000` in-flight + `2000` 排队。队列满或排队超时返回 429，并通过响应头暴露排队等待、在途数和队列数。`/admin/*`、`/admin/api/*`、`/health/*` 不进入该队列。归档/审计写入已通过 `ArchiveQueue` 削峰，支持队列上限、批量写入、处理数和丢弃数快照；上游请求优先复用应用生命周期内的共享 `AsyncClient`，并通过 `.env` 配置最大连接、keepalive 和超时。Dockerfile 当前使用 `uvicorn main:app --workers ${UVICORN_WORKERS:-4}`，不包含 `--reload`。

当前代码尚未具备路径 C 自动续约迁移结果页、Provider 切换演练页、替换后首次请求失败自动回滚、图片资产后台预览/下载页面、图片资产存储配额和清理任务、告警通知、文件安全、审批运行链路和中转站配额/速率只读观测能力。阶段 6A 的高并发能力已具备代码基础；数据治理能力已具备训练数据沉淀、覆盖分析、预览清理和手动清理基础闭环；仍需真实上游和 Docker 生产环境下完成阶梯压测、连接池观测、PostgreSQL 长时间运行、备份恢复、日志脱敏、数据清理演练和运维安全复核。

---

## 二、阶段完成情况

| 阶段 | 名称 | 当前状态 | 代码事实 |
|------|------|----------|----------|
| 阶段 1 | 透传中继 + 健康检查 | ✅ 已完成 | OpenAI-compatible `/v1/*` 通用透传、`/health/live`、`/health/ready`、Request ID、Header Policy、单上游路由已实现 |
| 阶段 2 | 弱扫描 MVP | ✅ 已完成 | Scanner、关键词/正则、block 伪装回复、desensitize 改写转发、弱规则集收敛、定时热加载、管理后台规则启停和手动热加载及对应测试已完成 |
| 阶段 3 | 归档 + 审计 | ✅ 已完成 | Chat 非流式/流式归档、block/desensitize 动作审计、文生图元数据归档、图片本体异步归档、图片资产状态 API、最近对话观测 API、SQLite 旧表缺列补齐、R1~R9 schema 预留和相关测试已完成 |
| 阶段 4 | 管理员认证 + 最小后台 | ✅ 已完成 | Basic Auth + IP 白名单、表单登录、后台静态页面鉴权、归档/审计/统计 API、规则管理 API、运行状态 API、管理员操作审计和最小静态后台已完成 |
| 阶段 5 | APIKey 管理 | ✅ 已完成 | `middleware/identity.py`、`governance/api_keys.py`、K-Sync 创建、加密存储、APIKey 有效性校验、上游 Key 映射、后台 CRUD、reveal、单条替换、CSV 批量替换和删除已吊销 Key 已完成；模型/token/资源能力权限由中转站负责 |
| 阶段 6 | KeyProvider + 中转站联通 | ✅ 核心能力已完成 | 已实现 Provider 抽象、`passthrough/static/oneapi_nanfu_yxai`、后台 Provider 创建、reveal/复制完整 Key、Provider-aware 吊销、`.env` 配置和 JSON 导入 |
| 阶段 6A | 单实例 Docker 生产稳定性、高并发治理与数据治理交付 | 🔄 工程能力已落地，待生产压测和运维演练验收 | `/v1/*` 有界并发队列、请求体大小限制、共享上游连接池、归档/审计队列、后台统计缓存、`/admin/api/runtime`、Docker worker 启动、训练数据沉淀、数据治理页面、覆盖分析、预览清理、手动清理和离线部署数据库保留策略已实现；仍需真实生产环境阶梯压测、连接池观测、数据清理演练和运维验收 |
| 阶段 7 | 扫描升级 | ⏸️ 暂不开发 | 当前仅保留规划记录，不进入近期开发；生产上线前不扩展完整 PII、分级策略和误报回归体系，继续使用阶段 2 已验证的低干扰规则集 |
| 阶段 8 | 可观测性 + 告警 | ⏸️ 暂不开发 | 当前仅保留规划记录，不进入近期开发；生产上线前不新增 Prometheus 指标、Webhook 告警、审计导出、图片资产后台预览/下载页面、存储配额和保留策略 |
| 阶段 9 | 审批 + 安全策略 + 审批链 | ⏸️ 暂不开发 | 当前仅保留规划记录，不进入近期开发；生产上线前不启用审批运行链路、策略绑定运行逻辑和审批链路由 |
| 阶段 10 | 远期能力 | ⏸️ 暂不开发 | 当前仅保留规划记录，不进入近期开发；生产上线前不启用文件解析、NER、配额、多上游和多租户能力 |

---

## 三、阶段 5/6 已实现能力明细

| 能力 | 文件 | 当前结果 |
|------|------|----------|
| APIKey 服务层 | `governance/api_keys.py` | 提供 K-Sync 创建、Key 哈希、前后缀提取、加密/解密、列表、详情、更新、吊销、删除已吊销 Key、reveal、单条替换、批量替换和 Provider 创建能力 |
| 加密存储 | `governance/api_keys.py` | 使用 `SAFETYHUB_DATA_KEY` 派生密钥生成加密信封，数据库不保存上游 Key 和 SafetyHub Key 明文；开发环境未配置时使用本地开发派生 Key，生产环境要求配置数据密钥 |
| Identity 中间件 | `middleware/identity.py` | 解析 `/v1/*` Authorization，匹配 `api_keys` 记录，校验 active/expired/revoked 状态，并构建 request identity |
| 资源权限边界 | `middleware/identity.py`、`proxy/relay.py`、`storage/models.py` | SafetyHub 只校验 APIKey 本地记录有效性并替换上游 Key；模型权限、token 额度、速率限制和资源能力权限由中转站判定，相关字段已从 SafetyHub schema、后台表单和 API 响应中删除 |
| 上游 Key 替换 | `proxy/relay.py`、`proxy/header_policy.py` | 已启用 Header Policy 的 `upstream_api_key` 分支，转发时用解密后的上游 Key 替换客户端 SafetyHub Key |
| 归档与审计身份绑定 | `proxy/relay.py` | Chat 和文生图归档写入 `user_id`、`api_key_id`；命中审计写入 `user_id` |
| Provider 抽象 | `governance/key_provider.py`、`governance/providers/*` | 支持 `passthrough`、`static`、`oneapi_nanfu_yxai`；Provider 创建失败回滚，本地落库失败尝试吊销已创建上游 Key |
| 后台 API | `admin/router.py`、`admin/schemas.py` | `/admin/api/api-keys` 支持手动创建、Provider 创建、列表、详情、更新、reveal、吊销、删除已吊销 Key、单条替换和 CSV 批量替换 |
| 后台页面 | `admin/static/api_keys.html`、`admin/static/js/app.js`、`admin/static/css/style.css` | APIKey 页面支持手动录入/Provider 创建、列表查看、按需显示/复制完整 Key、吊销、删除、单条替换和 CSV 批量替换，列表默认只展示前后缀 |
| 管理员操作审计 | `admin/router.py`、`storage/admin_ops.py` | 创建、更新、查看详情、reveal、吊销、删除、单条替换、批量替换均写入 `admin_operations` |
| SQLite 兼容 | `storage/database.py` | 对 `api_keys` 旧表补齐阶段 5/6 字段，包含 `safetyhub_key_encrypted`，避免已有 SQLite 数据库缺列导致写入失败 |
| 测试覆盖 | `tests/test_api_keys.py`、`tests/test_admin_stage4.py` | 覆盖 APIKey 服务、后台 CRUD、reveal、Provider 创建/吊销失败回滚、加密不回显、上游 Key 替换、allowlist 拒绝和阶段 4 兼容断言 |

---

## 四、阶段 6A 已实现能力与待验收项

| 能力 | 文件 | 当前结果 |
|------|------|----------|
| `/v1/*` 有界并发队列 | `middleware/concurrency_limit.py`、`main.py`、`tests/test_concurrency_limit.py` | 仅匹配 `/v1/` 路径；支持最大在途、最大排队、排队超时、队列满 429、响应头观测和运行快照；单元测试覆盖队列满、超时、排队释放和非 `/v1/*` 不受影响 |
| 请求体大小限制 | `middleware/request_limit.py`、`main.py`、`tests/test_api_keys.py` | 对 HTTP 请求体做大小保护，避免超大请求直接进入业务链路 |
| 共享上游连接池 | `runtime/upstream_client.py`、`main.py`、`proxy/relay.py` | 应用生命周期内创建共享 `httpx.AsyncClient`，按配置设置连接池、keepalive 和 timeout；缺省时保留兼容 fallback client |
| 归档/审计削峰 | `runtime/archive_queue.py`、`proxy/relay.py`、`storage/archive.py`、`storage/audit.py` | Chat 审计、Chat 归档和文生图元数据归档优先进入有界队列，后台批量写入；队列满或异常不阻塞主响应 |
| 后台统计缓存 | `runtime/admin_cache.py`、`admin/router.py` | `/admin/api/stats` 通过 TTL 缓存避免首页统计在压测期间反复重查询 |
| 运行状态 API | `admin/router.py`、`admin/schemas.py`、`admin/static/js/app.js`、`admin/static/index.html` | `/admin/api/runtime` 返回 worker pid、配置 worker 数、`/v1` 并发快照、归档队列快照、上游连接池配置和后台缓存配置；仪表盘可展示运行状态 |
| Docker 生产启动 | `Dockerfile`、`docker-compose.yml`、`.env.example` | Dockerfile 使用多 worker 生产命令，不使用 `--reload`；Compose 包含 PostgreSQL、SafetyHub、Nginx 和健康检查；`.env.example` 包含阶段 6A 配置项 |
| 透明中继兼容性修复（2026-06） | `proxy/relay.py`、`proxy/stream.py`、`proxy/header_policy.py` | 未脱敏请求改为 `content=raw_body` 字节透传，避免 httpx 重序列化破坏严格 JSON / 上游签名；流式 SSE 同步支持 `raw_body`；新增 `filter_response_headers` 统一剥离 hop-by-hop / `Content-Length` / `Content-Encoding`；非 `KNOWN_JSON_ENDPOINTS` 端点 JSON 解析失败由 400 降级为字节透传；64/64 中继相关测试通过 |
| 训练数据沉淀 | `storage/training.py`、`storage/models.py`、`proxy/relay.py` | Chat 请求 messages 与 assistant response 形成规范化 `trajectory`，写入 `training_conversations`，用于后续离线训练数据筛选；`analysis_status`、`covered_by_conversation_id`、`expires_at` 支持治理状态追踪 |
| 数据治理后台 | `storage/data_governance.py`、`admin/router.py`、`admin/static/data_governance.html`、`admin/static/js/app.js` | `/admin/api/data-governance/*` 支持治理摘要、覆盖分析启动/状态、清理预览和手动清理；页面提供保存模型摘要、治理摘要、覆盖分析参数和清理入口 |
| 覆盖分析算法 | `storage/data_governance.py`、`tests/test_data_governance.py` | 按 `user_id + api_key_id` 分组，倒序扫描每组记录，跳过已覆盖项，只做确定性 JSON 前缀比较；目标是保留每组最长有效轨迹集合；不按 `model` 分组，不使用 lookback，不引入 hash 派生表或外部通信 |
| 内网部署数据库保留策略 | `scripts/rebuild_runtime_tables_preserve_apikeys.py`、`交付运行手册/deploy_intranet_docker.sh` | 内网 Docker 升级时保留已有 `api_keys` 表，删除并重建当前系统需要的其他 SQLAlchemy 模型表；不从 JSON/SQL 重新导入 APIKey，避免覆盖内网已运行数据 |
| 自动化测试 | `tests/` | 历史全量测试基线为 `94 passed`；当前代码新增测试后最近一次本地复核为 `96 passed, 2 failed`，失败点集中在后台认证测试夹具未初始化 `message_archives` 表。新增数据治理专项测试覆盖跨模型同 user/key 的最长轨迹保留逻辑；生产能力判断以专项测试、Docker/真实上游验收和当前环境复跑结果为准 |

---

## 四 A、透明中继兼容性修复（2026-06）

> 背景：早期 SafetyHub 一律使用 `client.request(json=body)` 把请求重序列化后转发上游，导致只能应对 `test_llm_connection.py` 这种简单请求；主流 LLM 客户端（带签名、严格 JSON、自定义 key 顺序、压缩响应等）会出现上游 4xx/5xx 或客户端解码失败。本次修复参考 `temp/transparent_llm_proxy.py` 的设计，把 SafetyHub 中继层改造为字节级透传，同时保留扫描 / 脱敏 / 拦截 / 归档所有原有能力。

| 维度 | 修改前 | 修改后 |
|------|--------|--------|
| 请求字节路径 | 始终 `json=body` 重序列化 | `_select_relay_payload` 三态分流：脱敏走 `json=body`，其它走 `content=raw_body`，无 body 不带 |
| 流式发起 | `client.stream(json=body)` | `proxy_stream` / `collect_stream` 新增 `raw_body` 参数，优先字节透传 |
| 响应头处理 | 只删 `Content-Encoding`，但流式 chunk 仍是压缩字节，客户端解码错乱 | `filter_response_headers` 统一剥 hop-by-hop + `Content-Length` + `Content-Encoding`；httpx 默认自动解压 body，下行明文与头一致 |
| 未知 JSON POST 解析失败 | 一律 400 | `KNOWN_JSON_ENDPOINTS` 仍 400，其它端点降级字节透传 |
| 路由前缀 / 扫描范围 / 审计字段 | — | **完全不变** |

**字节流不变量**：

1. 客户端 → 上游：未脱敏路径 byte-for-byte 透传（保留 `messages` 顺序、空白、`ensure_ascii=false`、`tool_calls` 等结构）。
2. 上游 → 客户端：始终是明文 body + 不带 `Content-Encoding` 的响应头，客户端不会再做一次 gzip 解码。
3. 拦截：完全本地构造，不消耗上游配额。
4. 脱敏：仅当真正命中手机号才会改字节，其它 chat 请求与透明代理表现一致。

**关键决策**：仍然保留 `httpx`，**未**切换到 `aiohttp`；通过 curl 实测上游 `yxai-api.nanfu.com` 仅 HTTP/1.1，无 HTTP/2 push、无 socket 级 keepalive 调参需求、无 WebSocket 双工，所以保留 httpx 不影响兼容性。`upstream_keepalive_expiry=30s < 上游 nginx keepalive_timeout=75s`，可规避 `RemoteDisconnected`。

---

## 五、当前边界与风险点

| 优先级 | 未完成项 | 影响 |
|--------|----------|------|
| P0 | 真实 Docker 生产环境高并发阶梯压测尚未形成最终报告 | 阶段 6A 工程能力已落地，但是否满足 100 名员工峰值场景仍需真实上游、真实数据库和容器资源条件验证 |
| P0 | PostgreSQL 连接稳定性、备份恢复、索引和长期运行验证待补齐 | APIKey 切库已有脚本与配置，生产上线仍需验证容器重启、连接地址、备份恢复和高并发写入削峰 |
| P1 | 替换后首次请求验证新 upstream_key，失败时回滚旧 Key | 当前单条/批量替换会立即生效，但不自动触达上游验证新 Key 有效性；如新 Key 错误，需要管理员再次替换 |
| P1 | 标准加密库迁移 | 当前未新增第三方依赖，使用标准库加密信封满足不明文存储和完整性校验；后续如允许新增依赖，建议迁移到 Fernet 或 AES-GCM |
| P1 | Provider 自动续约迁移未实现 | 阶段 6 已支持 Provider 创建和同步吊销，但从旧中转站批量迁移到新 Provider 的路径 C、迁移进度页和失败重试仍待实现 |
| P1 | 图片资产后台预览/下载页面、存储配额和清理任务未实现 | 阶段 3 已保存图片本体与状态记录，但阶段 8 仍需补齐后台预览/下载、存储配额、保留策略和清理任务 |
| P1 | 告警通知未实现 | 高风险拦截不会推送企微/飞书 |

---

## 六、统一阶段口径

- 当前阶段统一为：**阶段 6A — 单实例 Docker 生产稳定性与高并发治理**。
- 阶段 1 至阶段 6 核心能力统一判定为：**已完成**。
- 阶段 6A 代码实现统一判定为：**工程能力已落地，生产压测和运维验收待完成**。
- 阶段 7 及之后统一判定为：**暂不开发**；相关内容仅作为长期规划保留，不进入当前生产上线范围，不作为上线阻塞项。
- 阶段 5 默认模式为 **K-Sync**：管理员录入的中转站 Key 同时作为客户端 SafetyHub Key 和上游 Key。
- 当管理员替换上游 Key 后，该记录自动进入 **K-Decoupled**：客户端 SafetyHub Key 不变，上游 Key 改为新中转站 Key。
- 阶段 5/6 的 APIKey 治理采用渐进启用策略：`api_keys` 表为空时保持历史透传；创建或导入第一条 APIKey 后 `/v1/*` 开始执行 APIKey 有效性校验和上游 Key 映射，不接管中转站的模型/token/资源权限判断。
- 后续文档不再使用“旧阶段 0 / 旧阶段 1 第一批 / 第二批 / 第三批”表达，全部按新版 10 阶段路线图描述。

---

## 七、下一步开发计划

### 7.1 下一批次：阶段 6A 生产验收与运维加固

| 优先级 | 任务 | 目标产出 |
|--------|------|----------|
| P0 | 高并发阶梯压测 | 在 Docker + PostgreSQL + 真实或等效上游环境下完成 ramp-up 和持续压测，记录 p50/p95/p99、错误率、队列满、排队超时、上游错误、归档降级和后台最大响应时间 |
| P0 | 管理端伴随验证 | 压测期间持续验证 `/health/live`、`/health/ready`、`/admin/`、`/admin/api/stats`、`/admin/api/runtime` 不被 `/v1/*` 队列阻塞 |
| P0 | 上游连接池观测 | 验证 `UPSTREAM_MAX_CONNECTIONS`、keepalive 和 pool timeout 生效，确认连接数不随请求总数无限增长 |
| P0 | PostgreSQL 生产稳定性验证 | 确认容器重启、连接地址、索引、备份恢复、连接池、写入削峰和长时间运行稳定性 |
| P1 | 生产配置安全复核 | 确认 `SAFETYHUB_DATA_KEY`、管理员密码、Provider 凭据、PostgreSQL 密码、IP 白名单、日志脱敏、Docker 日志滚动和请求大小限制满足生产要求 |
| P1 | 部署文档与压测报告归档 | 将实际 worker 数、并发参数、队列参数、数据库配置、容器资源、压测命令和结论写入交付材料 |
| P1 | 真实上游联通验收 | 使用受控测试 Key 验证 Chat 非流式、Chat 流式、文生图、APIKey 替换、Provider 创建和吊销主链路 |
| P2 | 非阻塞体验优化 | 仅处理不改变阶段范围的后台提示、错误文案和操作说明优化 |

### 7.2 暂停开发范围

| 阶段 | 当前处理口径 |
|------|--------------|
| 阶段 7 | 暂不开发完整 PII 规则、20+ 关键词正式启用、分级策略、绕过防护和误报回归；生产上线继续沿用阶段 2 已验证的低干扰规则集 |
| 阶段 8 | 暂不开发 Prometheus 指标、Webhook 告警、告警限流、仪表盘增强、审计 CSV 导出、图片资产后台预览/下载、存储配额和保留策略 |
| 阶段 9 | 暂不开发临时审批、安全策略、审批链路由、多级审批和超时升级 |
| 阶段 10 | 暂不开发文件安全、NER、全文搜索、配额、多上游、多租户、SSO/角色权限 |

---

## 八、当前项目结构摘要

```text
NF-SafetyHub/
├── main.py
├── config.py
├── dependencies.py
├── engine/
├── proxy/
├── observability/
├── storage/
│   ├── admin_ops.py
│   ├── archive.py
│   ├── audit.py
│   ├── database.py
│   ├── image_assets.py
│   └── models.py
├── runtime/
│   ├── admin_cache.py
│   ├── archive_queue.py
│   └── upstream_client.py
├── admin/
│   ├── router.py
│   ├── schemas.py
│   └── static/
│       ├── api_keys.html
│       ├── approvals.html
│       ├── archives.html
│       ├── blocks.html
│       ├── index.html
│       ├── login.html
│       ├── observations.html
│       ├── rules.html
│       ├── settings.html
│       ├── css/style.css
│       └── js/app.js
├── governance/
│   ├── api_keys.py
│   ├── key_provider.py
│   └── providers/
│       ├── passthrough.py
│       ├── static_key.py
│       └── oneapi_nanfu_yxai.py
├── middleware/
│   ├── auth.py
│   ├── concurrency_limit.py
│   ├── identity.py
│   └── request_limit.py
├── scripts/
│   ├── import_yxai_keys.py
│   ├── init_db.py
│   ├── migrate_apikeys_to_fernet.py
│   ├── migrate_sqlite_to_postgres.py
│   └── verify_postgres_migration.py
├── tests/
│   ├── test_admin_auth.py
│   ├── test_admin_image_assets.py
│   ├── test_admin_stage4.py
│   ├── test_api_keys.py
│   ├── test_archive.py
│   ├── test_audit.py
│   ├── test_concurrency_limit.py
│   ├── test_fake_response.py
│   ├── test_header_policy.py
│   ├── test_health.py
│   ├── test_image_assets.py
│   ├── test_keyword.py
│   ├── test_models.py
│   ├── test_observations.py
│   ├── test_regex.py
│   ├── test_relay.py
│   ├── test_relay_image_assets.py
│   ├── test_rules_config.py
│   ├── test_rules_reload.py
│   ├── test_scanner.py
│   └── test_upstream_router.py
└── 产品研发控制/
```

---

## 九、验证结果

| 验证项 | 命令 | 当前结果 |
|--------|------|----------|
| 全量单元测试 | `python -m pytest` 或已创建虚拟环境时使用 `.\.venv\Scripts\python.exe -m pytest` | 历史基线 `94 passed`；当前生产代码已继续演进，最近一次本地复核为 `96 passed, 2 failed`，失败集中在 `tests/test_admin_auth.py` 的后台认证测试夹具未初始化 `message_archives` 表。该问题属于测试夹具与当前生产代码演进不同步，不影响生产应用生命周期内的数据库初始化；生产上线判断应结合专项测试、Docker/真实上游联调和压测验收 |
| 并发闸门专项测试 | `pytest tests/test_concurrency_limit.py` | 覆盖响应头、非 `/v1/*` 不受限、队列满、排队超时、排队释放后放行 |
| APIKey / KeyProvider 专项测试 | `pytest tests/test_api_keys.py` | 覆盖手动创建、Provider 创建、reveal、上游 Key 替换、加密不回显、删除已吊销 Key 和请求体大小限制 |
| 图片资产专项测试 | `pytest tests/test_image_assets.py tests/test_relay_image_assets.py tests/test_admin_image_assets.py` | 覆盖文生图响应引用提取、本体归档、后台状态 API 和操作审计 |
| APIKey 迁移验证脚本 | `python scripts/verify_postgres_migration.py --tables api_keys` | 脚本已存在并用于 SQLite 到 PostgreSQL 迁移核对；生产验收时需复跑并记录最新结果 |
| 代码结构检查 | 文件系统检查 | 阶段 6A 新增 runtime、并发中间件、请求体限制、运行状态 API、Docker 生产启动和测试文件已纳入当前结构 |

---

## 十、当前注意事项

- 真实 `KEY_PROVIDER_PASSWORD`、`SAFETYHUB_DATA_KEY`、PostgreSQL 密码和上游 Key 只允许写入本地 `.env` 或部署密钥系统，不得写入文档、测试代码、命令日志或 `.env.example`。
- 生产环境启用阶段 5/6 前必须设置 `SAFETYHUB_DATA_KEY`，用于加密 `upstream_key_encrypted` 和 `safetyhub_key_encrypted`。
- 阶段 5/6 过渡策略为 `api_keys` 表为空时继续透传；创建或导入第一条 APIKey 后 `/v1/*` 开始要求客户端 Bearer Key 匹配有效记录。
- 后台列表和 API 列表响应默认只展示 Key 前后缀；管理员可通过受审计的 reveal 接口按需显示/复制完整 SafetyHub Key。
- Windows PowerShell 直接传中文 JSON 可能出现编码损坏，中文规则测试建议使用 UTF-8 请求体文件或 JSON Unicode 转义。
- 当前 block 拦截不会请求上游，但会写入归档和审计；阶段 8 告警暂不开发，不作为本次生产上线阻塞项。
- 当前 desensitize 只作用于 Chat Completions 请求侧 `messages` 文本字段；非 Chat 接口默认透明透传，响应内容原样透传。
- 当前运行环境建议使用 PostgreSQL；SQLite 旧库保留为迁移来源和回退参考，高并发生产按 PostgreSQL 口径验证。
- 多 worker 下阶段 6A 并发队列为进程内队列，容器总容量约等于每 worker 配置乘以 worker 数；如果调整 `UVICORN_WORKERS`，必须同步折算 `V1_MAX_INFLIGHT` 与 `V1_MAX_QUEUE_SIZE`。
- 当前数据库表通过 `create_all`、SQLite 缺列补齐和迁移脚本维持兼容，后续 schema 稳定后应评估引入 Alembic 或等效迁移机制。
