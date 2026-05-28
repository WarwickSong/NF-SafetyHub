# LLM-SafetyHub 当前开发进展和下一步规划

> 更新时间：2026-05-28  
> 当前阶段：阶段 1 — 核心安全链路  
> 当前状态：阶段 1 第二批“中继引擎”已完成，可进入阶段 1 第三批“消息归档”开发

---

## 一、当前执行进展

项目已完成阶段 0 基础设施搭建、阶段 1 第一批检测引擎，以及本轮阶段 1 第二批中继引擎。当前系统已经具备 `/v1/chat/completions` 入口、请求内容扫描、命中 block 后伪装回复、未命中时转发到上游、Header 安全透传、单上游路由和基础 SSE 流式转发能力。

### 1.1 阶段 0 已完成内容

| 类别 | 完成项 | 说明 |
|------|--------|------|
| 项目结构 | 创建核心目录结构 | 已创建核心模块目录、测试目录、部署目录和文档目录 |
| 应用入口 | 创建 `main.py` | 使用 FastAPI 生命周期管理，启动时初始化数据库、Scanner 和上游路由 |
| 配置管理 | 创建 `config.py` | 使用 `pydantic-settings` 读取 `.env` |
| 健康检查 | 创建 `observability/health.py` | 提供 `/health/live` 和 `/health/ready` |
| 请求追踪 | 创建 `observability/request_id.py` | 自动生成或透传 `X-Request-ID` |
| 数据库基线 | 创建 `storage/database.py`、`storage/models.py` | 已预留消息归档、审计日志、管理员操作审计三类基础表 |
| 容器化与部署 | 创建 Docker、Compose、Nginx、`.venv`、交付运行手册 | 已支持 Windows/Linux 的直接部署与 Docker 部署说明 |
| 研发测试控制 | 创建 `SafetyHub测试验证指导.md` | 明确 Windows/Linux/Docker/真实上游联调的测试方案、编码问题和令牌安全要求 |

### 1.2 阶段 1 第一批已完成内容：检测引擎

| 任务 ID | 完成项 | 文件 | 说明 |
|---------|--------|------|------|
| T1-01 | Scanner 数据模型 | `engine/models.py` | 定义 `ScannerResult`、`AggregatedScanResult` |
| T1-02 | Scanner 抽象基类 | `engine/base.py` | 定义 `scan`、`reload`、`name` 抽象接口 |
| T1-03 | 扫描器调度引擎 | `engine/scanner.py` | 支持链式调度、block 早停、warn 汇总、异常降级放行 |
| T1-03A | 文本归一化 | `engine/normalizer.py` | 支持 URL 解码、HTML unescape、NFKC、零宽字符移除、控制字符清理、空白压缩 |
| T1-04 | 初版规则配置 | `engine/rules_config.yaml` | 已配置 20 条关键词规则、10 条正则规则 |
| T1-05 | 关键词 Scanner | `engine/rules_keyword.py` | 支持关键词扫描、规则启停、命中片段脱敏、reload |
| T1-06 | 正则 Scanner | `engine/rules_regex.py` | 支持正则预编译、ignore_case、错误规则跳过、命中片段脱敏、reload |
| T1-07 | 规则热加载入口 | `reload()` / `reload_all()` | 已提供热加载接口，定时触发待后续接入 |

### 1.3 阶段 1 第二批已完成内容：中继引擎

| 任务 ID | 完成项 | 文件 | 说明 |
|---------|--------|------|------|
| T1-11 | SSE 流式处理 | `proxy/stream.py` | 支持上游 SSE 逐 chunk 透传和收集模式 |
| T1-11A | Header 透传/剥离策略 | `proxy/header_policy.py` | 默认剥离 Host、Hop-by-hop、Cookie、内部 Header 等高风险字段 |
| T1-11B | 单上游路由 | `proxy/upstream_router.py` | 支持默认上游地址构造，并预留模型/APIKey/capability 路由参数 |
| T1-12 | 中继转发入口 | `proxy/relay.py` | 实现 `/v1/chat/completions`，集成扫描、拦截、非流式转发和流式转发 |
| T1-13 | 伪装回复 | `proxy/fake_response.py` | 支持 OpenAI Chat Completions 兼容 JSON 与 SSE 伪装回复 |
| T1-21 | 应用集成 | `main.py` | 生命周期中初始化 Scanner 和 UpstreamRouter，并注册 `/v1` 路由 |
| 测试补充 | 中继相关测试 | `tests/test_relay.py`、`tests/test_fake_response.py`、`tests/test_header_policy.py`、`tests/test_upstream_router.py` | 覆盖拦截、放行转发、伪装回复、Header 策略、上游路由 |

---

## 二、验证结果

### 2.1 已执行验证

| 验证项 | 命令 | 结果 |
|--------|------|------|
| Python 编译检查 | `.\.venv\Scripts\python.exe -m compileall main.py config.py dependencies.py proxy engine governance file_security observability storage admin notify middleware scripts tests` | 通过 |
| 全量单元测试 | `.\.venv\Scripts\python.exe -m pytest` | 通过，25 passed |
| 真实上游基础联调 | `UPSTREAM_URL=https://yxai-api.nanfu.com` 后启动本地服务测试 | 通过，健康检查 ready；block 请求本地伪装回复；正常请求已触达上游并返回 401 |
| IDE 诊断 | Trae IDE Diagnostics | 通过，无诊断问题 |

### 2.2 当前可确认能力

- 应用启动时会初始化检测引擎和上游路由。
- `/v1/chat/completions` 路由已注册。
- 请求 messages 会被提取为文本并进入 Scanner 扫描。
- 命中 block 规则时不会请求上游，而是返回 OpenAI 兼容伪装回复。
- 未命中 block 时会按 Header Policy 转发到默认上游。
- 非流式响应可以透传上游 JSON。
- 流式请求具备 SSE 逐 chunk 透传工具。
- 当前测试总数从 17 个增加到 25 个，全部通过。
- `.env` 已设置本地上游 `UPSTREAM_URL=https://yxai-api.nanfu.com`。
- 真实上游基础触达已验证：无有效令牌时正常请求返回上游 401，说明放行路径已转发到上游。
- PowerShell 命令行直接传中文可能出现编码损坏，联调时建议使用 UTF-8 请求体文件或 JSON Unicode 转义。

---

## 三、与原规划的差异

| 原规划项 | 当前处理 | 差异原因 |
|----------|----------|----------|
| 阶段 1 完整核心链路包含归档 | 本轮完成中继和伪装回复，未实现归档 | 当前进展文档已将 `storage/archive.py` 归为阶段 1 后续任务；归档需要单独处理数据库写入、流式响应收集和失败降级 |
| 流式归档 | 当前只实现 SSE 透传工具，未做流式内容归档 | 归档属于下一批任务，避免把中继和存储逻辑一次性耦合过重 |
| 审计和告警 | 当前 block 只返回伪装回复，未写审计和告警 | 审计/告警属于阶段 2 管理能力或阶段 1 后续集成点 |
| 多上游路由 | 当前实现默认单上游，预留模型/APIKey/capability 参数 | v1.0 规划默认单上游，多上游策略后续启用 |
| 真实上游联调 | 已完成基础触达测试，正常请求无有效令牌时返回上游 401 | 已确认 `UPSTREAM_URL=https://yxai-api.nanfu.com` 生效；完整成功回复需使用有效令牌，但令牌不能写入命令日志或文件 |

---

## 四、当前项目结构摘要

```text
NF-SafetyHub/
├── main.py
├── config.py
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
├── tests/
│   ├── test_fake_response.py
│   ├── test_header_policy.py
│   ├── test_health.py
│   ├── test_keyword.py
│   ├── test_regex.py
│   ├── test_relay.py
│   ├── test_rules_config.py
│   ├── test_scanner.py
│   └── test_upstream_router.py
├── 交付运行手册/
└── 产品研发控制/
    └── SafetyHub测试验证指导.md
```

---

## 五、下一步规划

下一步进入 **阶段 1 第三批：消息归档**。

### 5.1 阶段 1 第三批任务

| 优先级 | 任务 | 目标产出 |
|--------|------|----------|
| P0 | 实现 `storage/archive.py` | ArchiveWriter + ArchiveReader，支持写入和基础查询 |
| P0 | 集成非流式归档 | 正常转发和伪装回复路径写入归档 |
| P0 | 集成流式归档 | 使用 `SSEStreamProxy.collect_stream` 收集完整响应后归档 |
| P0 | 增加归档测试 | 覆盖正常请求、拦截请求、归档失败不影响响应 |
| P1 | 归档失败降级 | 数据库写入异常不能影响主链路 |

### 5.2 阶段 1 后续任务

| 优先级 | 任务 | 目标产出 |
|--------|------|----------|
| P1 | 接入基础审计事件 | 记录 block/warn 检测结果，为阶段 2 审计查询打基础 |
| P1 | 接入规则定时热加载 | 使用 `rules_reload_interval` 周期调用 `reload_all()` |
| P1 | 真实上游受控联调 | 使用有效测试 token，在不落盘、不进入日志的前提下验证非流式和流式成功响应 |

### 5.3 阶段 1 验收目标

- 正常请求能通过 `/v1/chat/completions` 转发到上游。
- 命中 block 规则的请求不会发往上游，而是返回伪装回复。
- 命中 warn 规则的请求继续放行，并保留检测结果。
- 流式请求可以逐 chunk 透传。
- 请求和响应可以写入 SQLite 归档表。
- 检测引擎、中继、伪装回复和归档测试全部通过。

---

## 六、当前注意事项

- 当前项目根目录 `.venv` 已可用于本地运行、测试和直接部署。
- 生产 `.env` 必须配置强 `ADMIN_PASSWORD` 和真实 `UPSTREAM_URL`。
- 当前中继入口已可用，`.env` 已配置本地上游 `https://yxai-api.nanfu.com`。
- 有效上游令牌属于敏感凭据，不应写入 `.env.example`、文档、测试代码或会被记录的命令日志。
- 当前 block 拦截不会请求上游，但尚未写入归档、审计和告警。
- 当前规则命中片段已做脱敏，后续日志、审计、告警仍必须避免输出 prompt 原文和 APIKey 明文。
- 当前数据库表仍通过 `create_all` 创建，模型稳定后应引入 Alembic 或等效迁移机制。
