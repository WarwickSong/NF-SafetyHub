# LLM-SafetyHub 当前开发进展和下一步规划

> 更新时间：2026-06-04  
> 当前阶段：阶段 6 — KeyProvider + 中转站联通准备启动  
> 当前状态：阶段 1 OpenAI-compatible `/v1/*` 透传中继与健康检查已完成；阶段 2 弱扫描 MVP 已完成；阶段 3 归档 + 审计已完成；阶段 4 管理员认证 + 最小后台框架已完成；阶段 5 APIKey 管理已完成，包含 K-Sync 默认、加密存储、identity 中间件、后台 CRUD、单条/CSV 批量替换上游 Key 和管理员操作审计。APIKey 的模型权限、token 额度、资源能力权限统一由中转站作为权威系统管理，SafetyHub 只做安全治理和上游 Key 映射。

---

## 一、实际代码状态

本状态基于当前仓库代码检查与测试结果。当前代码已经具备 FastAPI 应用入口、健康检查、Request ID、OpenAI-compatible `/v1/*` 通用中继转发、Header 安全透传、单上游路由、Scanner 调度、关键词/正则扫描、block 拦截伪装回复、请求侧手机号脱敏改写转发、SSE 透传与完整流式归档、规则定时热加载、管理后台规则启停和手动热加载、管理 API 和静态页面 Basic Auth + IP 白名单、Chat 归档/审计写入、正式归档/审计分页筛选和详情 API、统计概览 API、管理员操作审计、最小静态后台、文生图元数据归档、最近对话观测 API、SQLite 旧表缺列补齐、R1~R9 schema 预留和 timezone-aware UTC 时间字段。

阶段 5 已新增 `governance/api_keys.py`、`middleware/identity.py`、后台 APIKey CRUD 接口和 `admin/static/api_keys.html` 可操作页面。SafetyHub 当前支持管理员手动录入已有中转站 Key，默认以 K-Sync 模式保存；数据库仅保存哈希、前后缀和加密后的上游 Key，不在后台列表返回 Key 明文。启用 APIKey 后，`/v1/*` 请求会按客户端 Authorization 查询 `api_keys`，校验本地记录是否存在、active/revoked/expired 状态是否有效，并用解密后的上游 Key 替换转发到中转站的 Authorization。模型权限、token 额度、速率限制和资源能力权限由中转站负责，SafetyHub 不做模型/能力 allowlist 拦截，相关字段已从当前 schema、后台表单和 API 响应中删除。若数据库中还没有任何 APIKey，`/v1/*` 会保持阶段 1-4 的过渡透传行为，便于上线迁移。

当前代码尚未具备 KeyProvider 具体适配器、中转站联通创建 Key、替换后首次请求失败自动回滚、文生图图片本体异步归档、告警通知、文件安全、审批运行链路和中转站配额/速率只读观测能力。

---

## 二、阶段完成情况

| 阶段 | 名称 | 当前状态 | 代码事实 |
|------|------|----------|----------|
| 阶段 1 | 透传中继 + 健康检查 | ✅ 已完成 | OpenAI-compatible `/v1/*` 通用透传、`/health/live`、`/health/ready`、Request ID、Header Policy、单上游路由已实现 |
| 阶段 2 | 弱扫描 MVP | ✅ 已完成 | Scanner、关键词/正则、block 伪装回复、desensitize 改写转发、弱规则集收敛、定时热加载、管理后台规则启停和手动热加载及对应测试已完成 |
| 阶段 3 | 归档 + 审计 | ✅ 已完成 | Chat 非流式/流式归档、block/desensitize 动作审计、文生图元数据归档、最近对话观测 API、SQLite 旧表缺列补齐、R1~R9 schema 预留和相关测试已完成 |
| 阶段 4 | 管理员认证 + 最小后台 | ✅ 已完成 | Basic Auth + IP 白名单、表单登录、后台静态页面鉴权、归档/审计/统计 API、规则管理 API、管理员操作审计和最小静态后台已完成 |
| 阶段 5 | APIKey 管理 | ✅ 已完成 | `middleware/identity.py`、`governance/api_keys.py`、K-Sync 创建、加密存储、APIKey 有效性校验、上游 Key 映射、后台 CRUD、单条替换和 CSV 批量替换上游 Key 已完成；模型/token/资源能力权限由中转站负责 |
| 阶段 6 | KeyProvider + 中转站联通 | ⏳ 待开始 | 暂无 Provider 抽象和适配器，当前阶段 5 仍以手动录入已有中转站 Key 为主 |
| 阶段 7 | 扫描升级 | ⏳ 待开始 | 当前已有 20 条关键词 + 10 条正则配置，扩展规则保留但默认关闭，尚未形成阶段 7 的完整 PII、分级策略和误报回归体系 |
| 阶段 8 | 可观测性 + 告警 | ⏳ 待开始 | 无 Prometheus 指标、Webhook 告警、告警限流、审计导出、文生图图片本体异步归档、后台预览/下载、存储配额和保留策略 |
| 阶段 9 | 审批 + 安全策略 + 审批链 | ⏳ 待开始 | 无审批运行链路、策略绑定运行逻辑和审批链路由 |
| 阶段 10 | 远期能力 | ⏳ 待开始 | `file_security/` 仅有包初始化文件，无文件解析、NER、配额、多上游和多租户能力 |

---

## 三、阶段 5 已实现能力明细

| 能力 | 文件 | 当前结果 |
|------|------|----------|
| APIKey 服务层 | `governance/api_keys.py` | 提供 K-Sync 创建、Key 哈希、前后缀提取、加密/解密、列表、详情、吊销、单条替换和批量替换能力 |
| 加密存储 | `governance/api_keys.py` | 使用 `SAFETYHUB_DATA_KEY` 派生密钥生成加密信封，数据库不保存上游 Key 明文；开发环境未配置时使用本地开发派生 Key，生产环境要求配置数据密钥 |
| Identity 中间件 | `middleware/identity.py` | 解析 `/v1/*` Authorization，匹配 `api_keys` 记录，校验 active/expired/revoked 状态，并构建 request identity |
| 资源权限边界 | `middleware/identity.py`、`proxy/relay.py`、`storage/models.py` | SafetyHub 只校验 APIKey 本地记录有效性并替换上游 Key；模型权限、token 额度、速率限制和资源能力权限由中转站判定，相关字段已从 SafetyHub schema、后台表单和 API 响应中删除 |
| 上游 Key 替换 | `proxy/relay.py`、`proxy/header_policy.py` | 已启用 Header Policy 的 `upstream_api_key` 分支，转发时用解密后的上游 Key 替换客户端 SafetyHub Key |
| 归档与审计身份绑定 | `proxy/relay.py` | Chat 和文生图归档写入 `user_id`、`api_key_id`；命中审计写入 `user_id` |
| 后台 API | `admin/router.py`、`admin/schemas.py` | `/admin/api/api-keys` 支持创建、列表、详情、吊销、单条替换和 CSV 批量替换 |
| 后台页面 | `admin/static/api_keys.html`、`admin/static/js/app.js`、`admin/static/css/style.css` | APIKey 页面支持新建 K-Sync、列表查看、吊销、单条替换和 CSV 批量替换，列表只展示前后缀 |
| 管理员操作审计 | `admin/router.py`、`storage/admin_ops.py` | 创建、查看详情、吊销、单条替换、批量替换均写入 `admin_operations` |
| SQLite 兼容 | `storage/database.py` | 对 `api_keys` 旧表补齐阶段 5 字段，避免已有 SQLite 数据库缺列导致写入失败 |
| 测试覆盖 | `tests/test_api_keys.py`、`tests/test_admin_stage4.py` | 覆盖 APIKey 服务、后台 CRUD、加密不回显、上游 Key 替换、allowlist 拒绝和阶段 4 兼容断言 |

---

## 四、阶段 5 边界与风险点

| 优先级 | 未完成项 | 影响 |
|--------|----------|------|
| P1 | 替换后首次请求验证新 upstream_key，失败时回滚旧 Key | 当前单条/批量替换会立即生效，但不自动触达上游验证新 Key 有效性；如新 Key 错误，需要管理员再次替换 |
| P1 | 标准加密库迁移 | 当前未新增第三方依赖，使用标准库加密信封满足不明文存储和完整性校验；后续如允许新增依赖，建议迁移到 Fernet 或 AES-GCM |
| P1 | KeyProvider 未实现 | 阶段 5 仅支持手动录入已有中转站 Key，自动创建/续约/迁移放入阶段 6 |
| P1 | 文生图图片本体异步归档未实现 | 阶段 8 无法提供图片资产预览/下载、存储配额和保留策略 |
| P1 | 告警通知未实现 | 高风险拦截不会推送企微/飞书 |

---

## 五、统一阶段口径

- 当前阶段统一为：**阶段 6 — KeyProvider + 中转站联通准备启动**。
- 阶段 1 至阶段 5 统一判定为：**已完成**。
- 阶段 5 默认模式为 **K-Sync**：管理员录入的中转站 Key 同时作为客户端 SafetyHub Key 和上游 Key。
- 当管理员替换上游 Key 后，该记录自动进入 **K-Decoupled**：客户端 SafetyHub Key 不变，上游 Key 改为新中转站 Key。
- 阶段 5 的 APIKey 治理采用渐进启用策略：`api_keys` 表为空时保持历史透传；创建第一条 APIKey 后 `/v1/*` 开始执行 APIKey 有效性校验和上游 Key 映射，不接管中转站的模型/token/资源权限判断。
- 后续文档不再使用“旧阶段 0 / 旧阶段 1 第一批 / 第二批 / 第三批”表达，全部按新版 10 阶段路线图描述。

---

## 六、下一步开发计划

### 6.1 下一批次：阶段 6 KeyProvider + 中转站联通

| 优先级 | 任务 | 目标产出 |
|--------|------|----------|
| P0 | ⏳ 设计 `KeyProvider` 抽象 | 统一 create/revoke/rotate/validate/list 接口，relay 不感知具体中转站 |
| P0 | ⏳ 实现 passthrough/static Provider | 保持阶段 5 手动录入能力，并为 Provider 切换提供默认实现 |
| P0 | ⏳ 实现 openai-compatible/oneapi Provider 适配边界 | 支持按配置调用中转站创建 Key 或验证 Key |
| P0 | ⏳ 后台创建表单接入 Provider 创建 | 管理员可选择手动录入或由中转站 Provider 创建 |
| P1 | ⏳ 替换后首次请求验证与失败回滚 | 降低管理员录入错误上游 Key 造成的业务中断风险 |
| P1 | ⏳ Provider 操作审计与迁移结果页 | 创建、吊销、迁移、失败重试均可追溯 |

### 6.2 后续批次概览

| 阶段 | 目标 |
|------|------|
| 阶段 6 | KeyProvider 抽象、passthrough/static/oneapi/openai_compat Provider、中转站联通创建和迁移 |
| 阶段 7 | 完整 PII 规则、20+ 关键词规则正式启用、分级策略、绕过防护、误报回归，沿用阶段 2 已完成的启停和热加载机制 |
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
│   └── api_keys.py
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
| 阶段 5 专项测试 | `conda run -n safetyhub python -m pytest tests/test_api_keys.py -vv -s` | 通过，4 passed |
| 全量单元测试 | `C:\Users\Zhihua Song\.conda\envs\safetyhub\python.exe -m pytest` | 通过，66 passed |
| 测试覆盖范围 | `tests/` | admin_auth、admin_stage4、api_keys、health、keyword、regex、scanner、fake_response、relay、header_policy、upstream_router、rules_config、rules_reload、archive、audit、models、observations |
| 代码结构检查 | 文件系统检查 | 阶段 5 APIKey 服务层、identity 中间件、后台接口、前端页面、SQLite 兼容和测试均已补齐 |

备注：本次全量测试先尝试 `conda run -n safetyhub python -m pytest` 时遇到 Conda 自身异常退出，随后使用该环境 Python 绝对路径绕过 Conda 插件异常完成验证，业务测试结果为 66 passed。

---

## 九、当前注意事项

- 当前 `.env` 可配置真实 `UPSTREAM_URL`，但真实上游令牌不得写入文档、测试代码、命令日志或 `.env.example`。
- 生产环境启用阶段 5 前应设置 `SAFETYHUB_DATA_KEY`，用于加密 `upstream_key_encrypted`。
- 阶段 5 过渡策略为 `api_keys` 表为空时继续透传；创建第一条 APIKey 后 `/v1/*` 开始要求客户端 Bearer Key 匹配有效记录。
- 后台列表和 API 响应只展示 Key 前后缀，不返回 APIKey 明文；管理员替换上游 Key 时需要二次确认操作流程。
- Windows PowerShell 直接传中文 JSON 可能出现编码损坏，中文规则测试建议使用 UTF-8 请求体文件或 JSON Unicode 转义。
- 当前 block 拦截不会请求上游，但会写入归档和审计；告警仍待阶段 8 实现。
- 当前 desensitize 只作用于 Chat Completions 请求侧 `messages` 文本字段；非 Chat 接口默认透明透传，响应内容原样透传。
- 当前数据库表通过 `create_all` 和 SQLite 缺列补齐维持兼容，后续 schema 稳定后应评估引入 Alembic 或等效迁移机制。
