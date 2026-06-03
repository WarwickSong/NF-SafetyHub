# LLM-SafetyHub 分工规划

> 更新时间：2026-06-02  
> 当前阶段：阶段 3 — 归档 + 审计准备启动（阶段 1 OpenAI-compatible `/v1/*` 通用透传与健康检查已完成；阶段 2 弱扫描 MVP 已完成）

---

## 一、分工总览

| 角色 | 负责人 | 职责范围 |
|------|--------|----------|
| 主控/集成 | 项目负责人 | main.py、config.py、storage/*、dependencies.py、tests/conftest.py、分支集成与发布 |
| 人员 A | 刘杨 | 前端 + 管理后台 API |
| 人员 B | 汤焱尧 | 拦截 + 解析 + 脱敏算法 |

---

## 二、刘杨 — 前端 + 管理后台 API

### 2.1 负责目录与文件

| 目录/文件 | 说明 | 当前状态 |
|-----------|------|----------|
| `admin/static/*` | 所有 HTML、CSS、JS（仪表盘、拦截记录、消息归档、审计日志、规则管理、审批、APIKey、文件安全、设置） | 占位页面，待开发 |
| `admin/router.py` | 管理后台 API 路由（`/admin/api/*`） | 未创建 |
| `admin/schemas.py` | Pydantic 请求/响应模型 | 未创建 |
| `middleware/auth.py` | 管理后台 Basic Auth + IP 白名单 | 未创建 |
| `middleware/logging.py` | 请求日志（脱敏） | 未创建 |
| `middleware/request_limit.py` | 请求大小/并发限制 | 未创建 |
| `middleware/error_handler.py` | 全局异常处理 | 未创建 |

### 2.2 页面开发任务

| 页面 | 路径 | 优先级 | 版本 | 说明 |
|------|------|--------|------|------|
| 仪表盘 | `/admin/` | P0 | 阶段 4 / 阶段 8 增强 | 安全态势总览 |
| 拦截记录 | `/admin/blocks` | P0 | 阶段 4 | 查看 block/warn/desensitize 事件 |
| 消息归档 | `/admin/archives` | P0 | 阶段 4 | 查询完整 Chat 对话记录，展示原始/脱敏 prompt；阶段 3 先写入数据 |
| 临时观测窗口 | `/admin/observations` | P0 | 阶段 3/4 上线初期 | 查看最近少量完整 Chat 对话、role 结构、原始/脱敏 messages、响应和命中动作，用于校验误拦截/误脱敏 |
| 文生图资产 | `/admin/image-assets` | P1 | 阶段 4 元数据查看 / 阶段 8 图片预览下载 | 阶段 3 先归档文生图元数据，阶段 8 增加图片本体预览/下载 |
| 审计日志 | `/admin/audits` | P0 | 阶段 4 | 规则命中和管理员操作审计 |
| 规则管理 | `/admin/rules` | P1 | 阶段 4 只读 / 阶段 7 启用 | 阶段 2 弱扫描规则说明，阶段 7 完整规则管理 |
| 系统设置 | `/admin/settings` | P1 | 阶段 4 / 阶段 6 增强 | 配置、Webhook、健康状态、Provider 类型 |
| APIKey/模型权限 | `/admin/api-keys` | P0 | 阶段 5 / 阶段 6 增强 | APIKey、模型、能力、K-Sync、上游替换、Provider 创建 |
| 审批记录 | `/admin/approvals` | P2 | 阶段 9 | 临时审批记录与处理状态 |
| 文件安全 | `/admin/files` | P2 | 阶段 10 | 文件扫描、拦截、脱敏记录 |

### 2.3 需实现的 API 接口

所有管理接口统一前缀 `/admin/api/*`，认证方式 Basic Auth + IP 白名单。

```
# 统计与态势
GET  /admin/api/stats              → 核心统计指标和趋势
GET  /admin/api/health             → 管理端展示用健康状态

# 消息归档
GET  /admin/api/archives           → 分页查询（支持 user_id/keyword/model/is_blocked/time_range 筛选）
GET  /admin/api/archives/{id}      → 单条归档详情
GET  /admin/api/archives/stats     → 归档统计

# 上线临时观测窗口
GET  /admin/api/observations/recent → 最近少量完整 Chat 对话样本（含 role、原始/脱敏 messages、响应、命中动作）

# 文生图资产（阶段 3 元数据，阶段 8 图片本体预览/下载）
GET  /admin/api/image-assets        → 文生图资产分页查询
GET  /admin/api/image-assets/{id}   → 文生图资产详情
GET  /admin/api/image-assets/{id}/download → 鉴权下载图片本体（阶段 8）

# 审计日志
GET  /admin/api/audits             → 安全审计分页查询
GET  /admin/api/audits/{id}        → 单条审计详情
GET  /admin/api/admin-ops          → 管理员操作审计列表

# 规则管理
GET  /admin/api/rules              → 规则列表（keyword + regex）
GET  /admin/api/rules/{id}         → 规则详情
POST /admin/api/rules/reload       → 触发规则热加载（阶段 7 启用）

# 告警与审批（告警阶段 8 启用，审批阶段 9 启用）
GET  /admin/api/alerts             → 告警记录
GET  /admin/api/approvals          → 审批记录

# 导出（阶段 8 启用）
GET  /admin/api/audits/export      → 安全审计导出
```

### 2.4 前端技术方案

| 项目 | 方案 | 说明 |
|------|------|------|
| 前端形态 | 静态 HTML + 原生 JavaScript + CSS | MVP 不引入 React/Vue，降低构建和部署复杂度 |
| 托管方式 | Nginx 静态文件 | `admin/static/` 挂载到 Nginx，API 由 FastAPI 提供 |
| 认证方式 | Basic Auth + IP 白名单 | 阶段 4 使用轻量认证 |
| 样式方案 | 单 CSS 文件 | `admin/static/css/style.css` |
| 公共逻辑 | 单 JS 文件 | `admin/static/js/app.js` |

### 2.5 开发策略：前端可先行 Mock

后端 API 未实现时，前端可在 `app.js` 中 mock `fetch` 返回值先行开发页面和交互，待后端接口就绪后切换为真实请求。接口路径和响应格式以 `admin/schemas.py` 中的 Pydantic 模型为准。

---

## 三、汤焱尧 — 拦截 + 解析 + 脱敏算法

### 3.1 负责目录与文件

| 目录/文件 | 说明 | 当前状态 |
|-----------|------|----------|
| `engine/base.py` | Scanner 抽象基类 | 已实现，后续可能扩展接口 |
| `engine/models.py` | ScannerResult 等数据模型 | 已实现，加字段不影响现有代码 |
| `engine/scanner.py` | 扫描器调度引擎 | 已实现，后续可能增加调度策略 |
| `engine/normalizer.py` | 文本归一化与绕过防护 | 已实现，后续可能增加归一化步骤 |
| `engine/rules_keyword.py` | 关键词规则 Scanner | 已实现，后续维护和优化 |
| `engine/rules_regex.py` | 正则规则 Scanner | 已实现，后续维护和优化 |
| `engine/rules_config.yaml` | 规则配置文件 | 已有 20 条关键词 + 10 条正则，后续扩充 |
| `proxy/relay.py` | OpenAI-compatible `/v1/*` 通用中继转发引擎 | 已实现 `/v1/*` 透明透传；Chat Completions 进入请求侧扫描与伪装拦截，非 Chat 接口默认透明透传，后续按需增加 desensitize 改写、资产归档和流式内容实时检测 |
| `proxy/fake_response.py` | 伪装回复生成器 | 已实现，后续可能增加回复模板 |
| `proxy/stream.py` | SSE 流式处理工具 | 已实现，后续可能增加流式扫描能力 |
| `proxy/header_policy.py` | Header 透传/剥离策略 | 已实现 |
| `proxy/upstream_router.py` | APIKey/模型到上游的路由 | 已实现基础版，后续启用多上游 |
| `file_security/*` | 文件解析、文本抽取、脱敏重写 | 未创建具体实现 |
| `governance/*` | 身份解析、APIKey 权限、模型策略、审批 | 未创建具体实现 |
| `notify/*` | 告警推送 | 未创建具体实现 |

### 3.2 核心开发任务

| 优先级 | 任务 | 目标产出 | 说明 |
|--------|------|----------|------|
| P0 | Chat 消息归档写入 | `storage/archive.py` | ArchiveWriter + ArchiveReader，支持非流式和流式 Chat 归档 |
| P1 | 文生图元数据归档 | `storage/archive.py` | 阶段 3 记录 prompt、model、参数和响应引用，不保存图片本体 |
| P1 | 文生图图片本体归档 | `storage/image_assets.py` | 阶段 8 异步保存图片本体，提供后台预览/下载、存储配额和保留策略 |
| P0 | 审计事件写入 | `storage/audit.py` | AuditWriter，记录 block/warn 检测结果 |
| P0 | 规则定时热加载 | 接入 `rules_reload_interval` 周期调用 `reload_all()` | 定时任务或启动时注册 |
| P1 | 新扫描器扩展 | NER 扫描器（命名实体识别）、语义分析预留 | 实现 `BaseScanner` 接口即可 |
| P1 | 文件安全 — 文本抽取 | `file_security/extractor.py` | PDF/Office/TXT 等文本抽取 |
| P1 | 文件安全 — 脱敏重写 | `file_security/sanitizer.py` | 文件内容脱敏与重写 |
| P1 | 文件安全 — 上传接口 | `file_security/router.py` | 文件上传/解析接口 |
| P1 | 告警推送 | `notify/webhook.py` | 企微/飞书 Webhook 推送 |
| P1 | 多上游路由 | `proxy/upstream_router.py` 扩展 | 按模型/APIKey/capability 路由 |
| P2 | 身份解析 | `governance/identity.py` | 用户/APIKey 身份解析 |
| P2 | APIKey 权限 | `governance/api_keys.py` | APIKey 元数据与权限 |
| P2 | 模型策略 | `governance/model_policy.py` | 模型访问策略 |
| P2 | 审批流程 | `governance/approval.py` | 临时放行审批 |
| P2 | 流式内容实时检测 | `proxy/stream.py` 扩展 | SSE 流式逐 chunk 检测 |

### 3.3 关键接口契约：BaseScanner

汤焱尧扩展新扫描器时，必须遵循以下接口。该接口已在 `engine/base.py` 中定义，不需要修改 `proxy/relay.py` 的任何代码。

```python
# engine/base.py — 已有定义
class BaseScanner(ABC):
    @abstractmethod
    async def scan(self, text: str) -> list[ScannerResult]: ...

    @abstractmethod
    async def reload(self) -> None: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


# engine/models.py — 已有定义
@dataclass(slots=True)
class ScannerResult:
    hit: bool
    rule_id: str = ""
    rule_name: str = ""
    level: str = "pass"           # "block" / "warn" / "pass"
    matched_text: str = ""        # 命中文本（脱敏后）
    position: tuple[int, int] = (0, 0)
    scanner_type: str = ""        # "keyword" / "regex" / "ner" / ...
    description: str = ""
```

**扩展规则**：
- 新扫描器只需继承 `BaseScanner` 并注册到 `ScannerOrchestrator`
- `ScannerResult` 可新增字段（`@dataclass(slots=True)` 允许默认值字段），但不得删除或改变现有字段语义
- 任何需要改动 `ScannerResult` 结构的变更必须通过主控 review

---

## 四、共享模块与协调机制

### 4.1 共享模块归属

| 目录/文件 | 归属 | 协调方式 |
|-----------|------|----------|
| `main.py` | 主控 | 两人都需要注册路由/中间件，由主控负责最终集成 |
| `config.py` | 主控 | 新增配置项需主控 review |
| `storage/models.py` | 主控 | ORM 模型是两边公共依赖，由主控维护 |
| `storage/database.py` | 主控 | 数据库连接管理 |
| `dependencies.py` | 共享 | FastAPI 依赖注入 |
| `tests/conftest.py` | 主控 | pytest fixtures 基础设施 |
| `observability/*` | 主控 | 健康检查和请求追踪 |

### 4.2 共享文件修改规则

1. **刘杨**或**汤焱尧**需要修改共享文件时，须提前告知主控，由主控修改或在 PR 中 review
2. 修改 `storage/models.py` 新增表定义时，须同时提供对应的 migration 或标注为 `create_all` 管理
3. 修改 `config.py` 新增配置项时，须同步更新 `.env.example`

---

## 五、Git 分支与工作流

### 5.1 分支策略

```
main ──────────────────────────────────────────────── （主控维护，修改须 PR）
  │
  ├── feat/admin-frontend ──── （刘杨：前端页面 + admin API）
  │
  └── feat/alg-scan-sanitize ── （汤焱尧：引擎扩展 + 文件安全 + 脱敏）
```

### 5.2 工作流规则

1. **不允许直接推 main**。主控负责 main 分支的合并和发布
2. **每人一个 feature 分支**。分支按模块划分，减少交叉
3. **合并前必须通过全量测试**：`.\.venv\Scripts\python.exe -m pytest`
4. **合并前必须通过编译检查**：`.\.venv\Scripts\python.exe -m compileall .`
5. **共享文件的修改由主控来做**。刘杨或汤焱尧需要修改共享文件时应先沟通

### 5.3 提交信息规范

```
feat(admin): 实现仪表盘页面
fix(engine): 修复关键词扫描大小写匹配问题
refactor(proxy): 提取中继转发公共逻辑
test(storage): 增加归档写入测试
```

格式：`类型(模块): 描述`

---

## 六、启动步骤

### 第 1 步（主控）：锁定接口契约

1. 创建 `admin/schemas.py`，定义所有 `/admin/api/*` 的 Pydantic 响应模型
2. 创建 `admin/router.py`，创建空路由函数（返回占位数据），确定 URL 路径和 HTTP 方法
3. 提交到 main

### 第 2 步（主控）：搭建基础设施

1. 实现 `middleware/auth.py`（Basic Auth + IP 白名单）
2. 创建 `tests/conftest.py`，提供 `TestClient(app)` 的 fixtures
3. 提交到 main

### 第 3 步（两人并行开始）

- **刘杨**：在 `feat/admin-frontend` 分支上开发，先做前端页面（可 mock 数据），再接入真实 API
- **汤焱尧**：在 `feat/alg-scan-sanitize` 分支上开发，扩展 `engine/` 扫描器、实现 `storage/archive.py` 和 `storage/audit.py`、实现 `file_security/`

### 第 4 步（主控）：定期集成与发布

- 每个 milestone 结束时，将两人的分支合并到 main，解决可能的冲突
- 运行全量测试和编译检查，确认一切正常

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 前端依赖后端 API，但 API 未实现 | 刘杨开发阻塞 | 前端先用 mock 数据开发；接口契约已在第 1 步锁定 |
| ScannerResult 结构变更影响主链路 | 汤焱尧的修改可能导致 relay 行为变化 | 结构变更须主控 review；加字段不影响，改字段须评估 |
| main.py 频繁修改导致合并冲突 | 集成成本高 | main.py 由主控一人维护，减少交叉 |
| 测试覆盖不够导致集成时才发现 bug | 延误交付 | 各自模块必须有单元测试；合并前必须全量测试通过 |
| 规则配置格式变更导致解析失败 | 汤焱尧修改 YAML 格式后刘杨的前端展示异常 | YAML 格式变更须同步更新 schemas.py 中的规则模型 |

---

## 八、验收标准

### 刘杨验收标准

- [ ] 仪表盘展示今日请求数、拦截数、告警数、活跃用户
- [ ] 拦截记录支持分页、筛选、详情查看
- [ ] 消息归档列表不展示完整 prompt/response，详情页按权限展示
- [ ] 审计日志不可在前端删除或修改
- [ ] 规则管理可查看规则列表和详情
- [ ] 所有管理接口受 Basic Auth 保护
- [ ] 后端异常时前端展示错误提示，不泄露堆栈信息

### 汤焱尧验收标准

- [ ] 非流式请求和流式请求的对话可写入 SQLite 归档表
- [ ] block/warn 事件可写入审计表
- [ ] 归档/审计写入失败不影响主链路转发
- [ ] 新扫描器继承 BaseScanner 并注册后自动生效
- [ ] 规则热加载定时执行，修改 YAML 后无需重启
- [ ] 文件上传可抽取文本并进入扫描流程
