# LLM-SafetyHub 测试验证指导

> 本文档定义 SafetyHub 在 Windows、Linux、Docker 和真实上游联调场景下的测试方法、注意事项和验收标准。  
> 当前重点覆盖阶段 1 透传中继 + 健康检查、阶段 2 检测/拦截/请求侧手机号脱敏/伪装回复/规则启停/规则热加载链路、阶段 3 Chat 非流式/流式归档、训练数据沉淀、文生图元数据归档、图片本体异步归档、图片资产状态 API、审计写入、最近对话观测 API、R1~R9 schema 预留、阶段 4 管理后台、阶段 5 APIKey 管理、K-Sync 默认、加密存储、APIKey 有效性校验、单条/CSV 批量替换上游 Key、阶段 6 KeyProvider 抽象与 Provider 创建/吊销，以及阶段 6A 高并发治理、数据治理覆盖分析和内网离线部署数据库保留策略。模型权限、token 额度和资源能力权限由中转站验证。阶段 7 及之后暂不开发；当前测试重点收敛到阶段 6A 单实例 Docker 生产稳定性、高并发治理、数据治理和部署验收，自动续约迁移、Provider 切换演练、审计告警、图片资产预览下载页面和存储治理仅保留为长期规划。

---

## 一、为什么需要这份指导

本项目在阶段 1 中继联调时暴露出两个容易被遗漏的问题：

1. **Windows PowerShell 中文编码问题**：直接在命令行中写中文 JSON，可能被当前终端编码破坏为 `?????`，导致关键词规则没有命中，从而错误放行到上游。
2. **上游令牌安全问题**：真实 Authorization Token 属于敏感凭据，不能写入 `.env.example`、文档、测试代码、命令历史或会被记录的自动化日志。

因此后续测试必须同时验证功能正确性、安全性和测试输入本身的可靠性。

---

## 二、测试分层

| 层级 | 目标 | 典型命令 |
|------|------|----------|
| L0 编译检查 | 确认 Python 文件无语法错误 | `python -m compileall ...` |
| L1 单元测试 | 验证模块级逻辑 | `pytest tests/test_*.py` |
| L2 集成测试 | 验证 FastAPI 生命周期、检测、拦截、转发 | `pytest` 全量 |
| L3 本地服务测试 | 启动 Uvicorn 后用 HTTP 请求验证接口 | `Invoke-RestMethod` / `curl` |
| L4 真实上游联调 | 验证真实 `UPSTREAM_URL` 和 Header 透传 | 手动输入 token 后请求 |
| L5 部署验证 | 验证 Docker/Linux/systemd 运行 | `docker compose ps`、`curl /health/ready` |

---

## 三、Windows 测试方案

### 3.1 准备环境

以下命令中的 `<SafetyHub项目根目录>` 表示当前电脑上的 SafetyHub 仓库根目录，请按实际路径替换。

```powershell
cd <SafetyHub项目根目录>
.\交付运行手册\setup_venv.ps1
```

### 3.2 编译检查

```powershell
.\.venv\Scripts\python.exe -m compileall main.py config.py dependencies.py proxy engine governance file_security observability storage admin notify middleware scripts tests
```

### 3.3 全量测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

当前参考基线：

```text
历史基线：94 passed
最近一次本地复核：96 passed, 2 failed
```

当前已知提示：`datetime.utcnow()` 弃用警告已修复，ORM 时间字段统一使用 timezone-aware UTC。当前生产代码已继续演进，固定通过数不再作为唯一验收口径；最近专项验证覆盖训练样本、上线观测、数据治理和中继链路，命令为 `.venv/bin/python -m pytest tests/test_admin_stage4.py tests/test_observations.py tests/test_data_governance.py tests/test_relay.py -q`，结果 `32 passed`。生产上线验收仍应以当前环境复跑、专项测试、Docker/真实上游联调和压测结果为准。

### 3.4 分模块测试

```powershell
.\交付运行手册\verify_engine.ps1
.\交付运行手册\verify_relay.ps1
.\交付运行手册\verify_venv.ps1
```

### 3.5 本地服务测试

启动服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/health/ready -Method Get
```

预期：

```json
{"status":"ready","checks":{"database":true,"rules":true}}
```

---

## 四、Linux 测试方案

### 4.1 准备环境

以下命令中的 `<SafetyHub项目根目录>` 表示当前机器上的 SafetyHub 仓库根目录，请按实际路径替换。

```bash
cd <SafetyHub项目根目录>
chmod +x 交付运行手册/*.sh
./交付运行手册/setup_venv.sh
```

### 4.2 编译检查

```bash
.venv/bin/python -m compileall main.py config.py dependencies.py proxy engine governance file_security observability storage admin notify middleware scripts tests
```

### 4.3 全量测试

```bash
.venv/bin/python -m pytest
```

### 4.4 分模块测试

```bash
./交付运行手册/verify_engine.sh
./交付运行手册/verify_relay.sh
./交付运行手册/verify_venv.sh
.venv/bin/python -m pytest tests/test_data_governance.py
```

`tests/test_data_governance.py` 用于验证当前覆盖分析核心语义：跨模型但同 `user_id + api_key_id` 的短轨迹可被最长轨迹覆盖，不同 user/key 不串组。

### 4.5 本地服务测试

```bash
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

另开终端验证：

```bash
curl http://127.0.0.1:8000/health/ready
```

---

## 五、Docker 测试方案

### 5.1 准备配置

```bash
cp 交付运行手册/.env.production.example .env
```

至少修改：

```text
UPSTREAM_URL=https://yxai-api.nanfu.com
ADMIN_PASSWORD=至少12位强密码
```

阶段 6A 单实例生产高并发治理建议补充，默认按 100 名员工同时使用 OpenClaw/Hermes/批量标注 Agent 的峰值生产场景规划。注意：代码默认值为每 worker `V1_MAX_INFLIGHT=150`、`V1_MAX_QUEUE_SIZE=200`、`UPSTREAM_MAX_KEEPALIVE_CONNECTIONS=150`；为达到 4 worker 容器总目标 1000 in-flight + 2000 排队，请在 `.env` 中显式设置如下生产推荐值：

```text
UVICORN_WORKERS=4
V1_MAX_INFLIGHT=250
V1_MAX_QUEUE_SIZE=500
V1_QUEUE_TIMEOUT_SECONDS=15
UPSTREAM_MAX_CONNECTIONS=200
UPSTREAM_MAX_KEEPALIVE_CONNECTIONS=100
UPSTREAM_TIMEOUT_POOL=5
ADMIN_STATS_CACHE_SECONDS=10
ARCHIVE_QUEUE_MAX_SIZE=5000
ARCHIVE_BATCH_SIZE=50
ARCHIVE_FLUSH_INTERVAL_SECONDS=1
ARCHIVE_MAX_PAYLOAD_BYTES=262144
```

上述示例表示单实例 Docker 内 4 worker，每 worker 最多 250 个 `/v1/*` 在途请求，容器总目标至少 1000 个在途请求；每 worker 最多 500 个排队请求，容器总目标至少 2000 个排队请求。若 worker 数变化，必须同步折算每 worker 参数；这些参数必须支持通过 `.env` 或等价部署配置修改。流式与非流式统一进入 `/v1/*` 队列，不单独拆分流式并发池。

### 5.2 启动

```bash
docker compose up --build -d
```

生产模式要求：

- Docker 启动命令不得包含 `--reload`。
- `/admin/*`、`/admin/api/*`、`/health/*` 不进入 `/v1/*` 并发队列。
- 当前 APIKey 已完成 SQLite 到 PostgreSQL 迁移，运行 `.env` 已切换 PostgreSQL；上线验证需确认 `/health/ready` 中 `database=true`。
- 内网离线升级部署采用“保留 `api_keys`，重建其他当前系统表”的策略：部署前必须确认 `SAFETYHUB_POSTGRES_DATA_DIR`、`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`DB_URL` 指向旧内网数据库；部署过程不从 JSON/SQL 重新导入 APIKey。
- 如后续短期回退 SQLite，应确认 WAL、busy timeout、归档截断和后台统计缓存策略已启用；高并发生产默认按 PostgreSQL 口径验证。

### 5.3 验证

```bash
docker compose ps
curl http://127.0.0.1:8080/health/live
curl http://127.0.0.1:8080/health/ready
```

阶段 6A 追加验证：

```bash
curl -sS -o /dev/null -w 'live code=%{http_code} total=%{time_total}\n' http://127.0.0.1:8080/health/live
curl -sS -o /dev/null -w 'ready code=%{http_code} total=%{time_total}\n' http://127.0.0.1:8080/health/ready
curl -sS -o /dev/null -w 'admin code=%{http_code} total=%{time_total}\n' http://127.0.0.1:8080/admin/
```

---

## 六、阶段 6A 高并发压测与生产稳定性验证

### 6.1 压测原则

| 原则 | 要求 |
|------|------|
| 阶梯加压 | 优先使用 ramp-up，从 50/100/200 逐步升到目标并发，至少覆盖 1000 in-flight + 2000 排队目标附近的压力，不直接从 1000 并发开始 |
| 记录配置 | 每次记录 worker 数、每 worker 并发上限、队列大小、队列超时、容器总 in-flight/queue 目标、上游连接池、数据库类型和归档策略 |
| 管理端伴随验证 | 压测期间持续验证 `/health/*` 和 `/admin/*` 是否可访问 |
| 失败可解释 | 区分安全拦截、队列满、排队超时、上游错误、数据库写入降级和客户端超时 |
| 单实例边界 | 不把水平扩展、按 Key 限流、上游熔断和流式单独并发池作为当前验收前提 |

### 6.2 推荐压测命令

```bash
python /var/www/temp/test_llm_throughput.py --mode ramp-up --start 50 --max 3000 --step 100 --duration 30
python /var/www/temp/test_llm_throughput.py --mode duration -c 3000 -d 120
```

执行顺序建议先 ramp-up，确认各级并发的 p95/p99、错误率和后台可用性，再执行固定 3000 并发持续 120 秒，用于覆盖默认 4 worker 下 1000 in-flight + 2000 排队的容量边界。

### 6.3 并发闸门验收

| 场景 | 预期 |
|------|------|
| 并发低于 `V1_MAX_INFLIGHT` | 请求直接进入业务链路，无排队或仅少量排队 |
| 并发高于 `V1_MAX_INFLIGHT` 且队列未满 | 请求等待令牌，响应中可观测 queue_wait_ms 或日志中可见排队耗时 |
| 队列满 | 新请求返回 429/503，不进入业务链路，不无限占用内存 |
| 排队超时 | 请求返回 429/503，错误信息可区分 queue timeout |
| 多 worker | 容器总在途约等于每 worker `V1_MAX_INFLIGHT` × worker 数 |

### 6.4 管理端可用性验收

压测期间并行执行：

```bash
for i in $(seq 1 30); do
  date
  curl -sS -o /dev/null -w 'live %{http_code} %{time_total}\n' http://127.0.0.1:8080/health/live
  curl -sS -o /dev/null -w 'ready %{http_code} %{time_total}\n' http://127.0.0.1:8080/health/ready
  curl -sS -o /dev/null -w 'admin %{http_code} %{time_total}\n' http://127.0.0.1:8080/admin/
  sleep 2
done
```

预期：

- `/health/live` 快速返回。
- `/health/ready` 不因 `/v1/*` 队列满而被拒绝。
- `/admin/` 可返回登录页或后台页面，不被 `/v1/*` 并发闸门阻塞。
- 已登录状态下 `/admin/api/stats` 返回短缓存结果或可接受延迟结果。

### 6.5 上游连接池与归档削峰验收

| 验收项 | 预期 |
|--------|------|
| 上游连接池 | 连接数受 `UPSTREAM_MAX_CONNECTIONS` 约束，不随请求总数无限增长 |
| 连接池等待 | `UPSTREAM_TIMEOUT_POOL` 超时能返回明确错误，不无限等待 |
| 归档队列 | 队列长度受 `ARCHIVE_QUEUE_MAX_SIZE` 约束 |
| 归档降级 | 队列满、数据库慢或写入失败时，主请求链路仍能返回响应 |
| 归档截断 | 超过 `ARCHIVE_MAX_PAYLOAD_BYTES` 的 prompt/response 保存截断标记和原始大小 |

### 6.6 压测报告最小字段

```text
测试时间：
代码版本：
Docker 镜像：
worker 数：
V1_MAX_INFLIGHT / V1_MAX_QUEUE_SIZE / V1_QUEUE_TIMEOUT_SECONDS：
容器总 in-flight / queue 目标：
UPSTREAM_MAX_CONNECTIONS / UPSTREAM_MAX_KEEPALIVE_CONNECTIONS：
数据库类型：SQLite / PostgreSQL
归档策略：同步 / 队列 / 采样 / 截断
压测命令：
总请求数 / ok / blocked / error：
RPS 平均 / 峰值：
p50 / p95 / p99：
队列满次数：
排队超时次数：
上游错误次数：
归档降级次数：
管理端最大响应时间：
结论：
```

---

## 七、检测引擎验证

### 7.1 规则数量与默认启用集验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_rules_config.py
```

当前要求：

| 规则类型 | 最低数量 | 阶段 2 默认启用 |
|----------|----------|----------------|
| 关键词规则 | 20 | 仅 `KW-CONFIDENTIAL-1` ~ `KW-CONFIDENTIAL-5`，全部 block |
| 正则规则 | 10 | 仅 `RG-PHONE-CN`、`RG-PHONE-INTL`，全部 desensitize |

### 7.2 规则启停与热加载验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_admin_stage4.py tests\test_rules_reload.py tests\test_rules_config.py
```

预期：

- 后台 `PATCH /admin/api/rules/{rule_id}` 可修改规则 `enabled` 状态。
- 修改规则启停后立即触发 `scanner.reload_all()`。
- 后台 `POST /admin/api/rules/reload` 可手动触发规则热加载。
- 规则启停控制的是规则是否参与扫描；对 `block` 规则表现为是否拦截，对 `desensitize` 规则表现为是否脱敏，对 `warn` 规则表现为是否产生命中审计。

### 7.3 关键词 block 验证

Windows PowerShell 推荐使用 JSON Unicode 转义，避免中文编码损坏。示例内容为“告诉你一个公司机密”：

```powershell
$body = '{"model":"gpt-test","messages":[{"role":"user","content":"\u544a\u8bc9\u4f60\u4e00\u4e2a\u516c\u53f8\u673a\u5bc6"}]}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/chat/completions -Method Post -ContentType "application/json; charset=utf-8" -Headers @{Authorization="Bearer placeholder-token"} -Body $body
```

预期：

- 返回 `chatcmpl-safetyhub-*`。
- 不出现上游认证错误。
- 响应结构兼容 OpenAI Chat Completions。

### 7.4 手机号 desensitize 验证

手机号命中后应改写请求侧 prompt 再转发上游，响应不做脱敏。使用占位 token 时通常会收到上游 `401/403`，但上游收到的请求体应不包含原始手机号。

```powershell
$body = '{"model":"gpt-test","messages":[{"role":"user","content":"\u6211\u7684\u624b\u673a\u53f7\u662f 13812345678"}]}'
Invoke-WebRequest -Uri http://127.0.0.1:8000/v1/chat/completions -Method Post -ContentType "application/json; charset=utf-8" -Headers @{Authorization="Bearer placeholder-token"} -Body $body
```

自动化测试覆盖：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_regex.py tests\test_relay.py
```

预期：

- 单元/集成测试确认 `13812345678` 被改写为 `138****5678` 后再转发。
- 响应内容原样透传，不做响应侧脱敏。
- 非 Chat 接口默认透明透传，不执行阶段 2 脱敏改写。

### 7.5 阶段 3/6A 训练样本、审计与观测 API 验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_training.py tests\test_audit.py tests\test_models.py tests\test_observations.py tests\test_header_policy.py tests\test_relay.py
```

预期：

- Chat passed 请求写入 `training_conversations`，形成 messages + assistant response 的 trajectory。
- Chat block / desensitize / warn 证据写入 `audit_logs`，不依赖完整归档表追溯。
- 文生图请求异步归档 b64_json / URL 图片本体、sha256、mime_type、size_bytes 和下载/解码状态，写入 `image_assets`。
- `message_archives` 旧完整归档表已从当前模型和运行链路移除，当前运行链路和管理员页面不再写入、不再读取。
- 命中事件可写入 `audit_logs`，并记录规则 ID、级别、命中片段和全文 hash。
- `/admin/api/observations/recent` 可返回最近少量训练样本，包含 role、messages、assistant response 和脱敏状态。
- APIKey 映射、审批、SafetyHub 安全策略相关 schema 预留表和字段可通过 `create_all` 创建；模型/token/资源权限和配额字段不进入 SafetyHub APIKey schema。
- Header 可选上游 Key 替换分支可测试，`upstream_api_key=None` 时透传行为不变。
- `/admin/api/*` 默认受 Basic Auth + IP 白名单保护。
- 训练样本、审计或图片资产异常不影响 relay 主链路。

当前边界：阶段 3 已保存文生图图片本体和状态记录；图片资产后台预览/下载页面、存储配额和保留策略放入阶段 8。

### 7.6 阶段 5/6 APIKey 与 KeyProvider 验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_api_keys.py
```

预期：

- `governance/api_keys.py` 可创建 K-Sync APIKey，`key_hash`、`upstream_key_encrypted`、`safetyhub_key_encrypted` 均不保存明文。
- 管理后台 `/admin/api/api-keys` 可手动创建、Provider 创建、列表、详情、reveal、吊销 APIKey。
- `governance/key_provider.py` 抽象和 `oneapi_nanfu_yxai` Provider 支持创建、获取完整 Key、分页列表和吊销中转站 Key。
- Provider 创建默认 K-Sync，创建成功返回完整 SafetyHub Key；列表默认只展示前后缀。
- reveal 接口按需返回完整 SafetyHub Key，设置 `Cache-Control: no-store`，并写入管理员操作审计。
- Provider-aware 吊销必须先删除中转站 Key，成功后才标记本地 revoked；删除失败不得假成功。
- 单条替换上游 Key 后 `is_decoupled=True`，客户端 SafetyHub Key 不变，且不覆盖 Provider 创建记录的真实 `upstream_key_id`。
- CSV 批量替换支持 `api_key_id,new_upstream_key` 或 `safetyhub_key_prefix,new_upstream_key`。
- `/v1/*` 启用 APIKey 后会用解密后的上游 Key 替换转发 Authorization。
- APIKey 表、后台表单和 API 响应均不包含 `model_allowlist` 或 `capability_allowlist`；模型权限、token 额度和资源能力权限由中转站返回最终结果。
- APIKey 创建、查看、reveal、吊销、替换操作写入管理员操作审计。

阶段 5/6 过渡边界：如果 `api_keys` 表为空，`/v1/*` 暂保持阶段 1-4 的历史透传行为；创建或导入第一条 APIKey 后开始执行 APIKey 有效性校验和上游 Key 映射，不接管中转站资源权限。

历史 yxai Key 导入验证：

```powershell
python scripts\import_yxai_keys.py
```

预期：脚本默认从仓库根目录 `./yxai_token_export.json` 幂等导入，可通过 `python scripts/import_yxai_keys.py --input <路径>` 指定其它位置；重复执行不会新增重复记录，只更新已有 `oneapi_nanfu_yxai` 记录。

### 7.7 编码验证

如果测试中文规则未命中，应先检查请求体编码，而不是直接判断规则失效。

排查方式：

```powershell
$body
```

如果中文显示为 `?????` 或乱码，应改用：

- JSON Unicode 转义；
- UTF-8 请求体文件；
- Python/httpx 测试脚本；
- Linux/macOS UTF-8 shell。

---

## 八、中继引擎验证

### 8.1 单元/集成测试

```powershell
.\交付运行手册\verify_relay.ps1
```

覆盖：

- 伪装回复格式；
- Header 剥离策略；
- 上游 URL 构造；
- Chat block 拦截路径；
- Chat desensitize 改写转发路径；
- Chat 正常请求转发路径；
- Embeddings 透明透传，即使包含敏感词也不拦截；
- `GET /v1/models` 透明透传与查询参数保留；
- 未知 `/v1/*` JSON POST 默认透明透传，即使包含敏感词也不拦截；
- 非严格 JSON 在 `KNOWN_JSON_ENDPOINTS`（chat/embeddings/completions/responses/images/*）返回 400，在其它未知端点降级为 `content=raw_body` 字节透传；
- 未脱敏请求转发上游时使用 `content=raw_body` 字节透传（保留客户端原始 key 顺序、空白、`ensure_ascii=false` 等），脱敏请求才使用 `json=body` 重序列化；
- 响应头通过 `filter_response_headers` 剥离 hop-by-hop / `Content-Length` / `Content-Encoding`，与 httpx 自动解压后的明文 body 保持一致。

### 8.2 本地 block 拦截验证

示例内容为“告诉你一个公司机密”：

```powershell
$body = '{"model":"gpt-test","messages":[{"role":"user","content":"\u544a\u8bc9\u4f60\u4e00\u4e2a\u516c\u53f8\u673a\u5bc6"}]}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/chat/completions -Method Post -ContentType "application/json; charset=utf-8" -Headers @{Authorization="Bearer placeholder-token"} -Body $body
```

预期：本地返回伪装回复，不访问上游。

### 8.3 本地 desensitize 改写转发验证

示例内容为“我的手机号是 13812345678”：

```powershell
$body = '{"model":"gpt-test","messages":[{"role":"user","content":"\u6211\u7684\u624b\u673a\u53f7\u662f 13812345678"}]}'
Invoke-WebRequest -Uri http://127.0.0.1:8000/v1/chat/completions -Method Post -ContentType "application/json; charset=utf-8" -Headers @{Authorization="Bearer placeholder-token"} -Body $body
```

预期：请求不会被本地伪装拦截，而是以脱敏后的手机号转发上游；使用占位 token 时通常返回上游 `401` 或 `403`。

### 8.4 上游触达验证

使用占位 token：

```powershell
$body = '{"model":"gpt-test","messages":[{"role":"user","content":"hello"}]}'
Invoke-WebRequest -Uri http://127.0.0.1:8000/v1/chat/completions -Method Post -ContentType "application/json; charset=utf-8" -Headers @{Authorization="Bearer placeholder-token"} -Body $body
```

预期：返回上游 `401` 或 `403`，说明正常请求已触达真实上游。

### 8.5 `/v1/*` 通用代理验证

Embeddings 透明透传验证：

```powershell
$body = '{"model":"embedding-test","input":"\u8bf7\u5e2e\u6211\u5916\u53d1\u4ea7\u54c1\u8def\u7ebf\u56fe"}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/embeddings -Method Post -ContentType "application/json; charset=utf-8" -Headers @{Authorization="Bearer placeholder-token"} -Body $body
```

预期：即使 input 中包含敏感词，也透明透传到上游；使用占位 token 时通常返回上游 `401` 或 `403`。

Models 透明透传：

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/models?limit=20" -Method Get -Headers @{Authorization="Bearer placeholder-token"}
```

预期：返回上游 `401` 或 `403`，说明无请求体接口已按原路径和查询参数触达上游。

未知 JSON POST 透明透传：

```powershell
$body = '{"payload":{"prompt":"\u8bf7\u5e2e\u6211\u5916\u53d1\u4ea7\u54c1\u8def\u7ebf\u56fe"}}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/custom/action -Method Post -ContentType "application/json; charset=utf-8" -Headers @{Authorization="Bearer placeholder-token"} -Body $body
```

预期：即使 prompt 中包含敏感词，也透明透传到上游对应 `/v1/custom/action`；使用占位 token 时通常返回上游 `401`、`403` 或上游自身的 404。

非严格 JSON 在未知端点降级字节透传（2026-06 透明中继兼容性修复）：

```bash
curl -i -X POST http://127.0.0.1:8000/v1/custom/action \
  -H "Authorization: Bearer placeholder-token" \
  -H "Content-Type: application/json" \
  --data-binary $'{\n  "payload": {\n    "prompt": "demo",\n    /* trailing comment */\n  }\n}'
```

预期：

- 该 body 不是严格 JSON（含尾逗号 / 行内注释），由于路径不在 `KNOWN_JSON_ENDPOINTS`，SafetyHub 不再返回 400，而是把原始字节直接透传给上游；
- 同样的 body 发到 `/v1/chat/completions` 或 `/v1/embeddings` 应仍然返回 400 `invalid json body`，以保证扫描 / 归档需要的 dict 结构。

未脱敏请求字节透传验证（手工，需要抓包配合）：

- 客户端发送一个带 `tool_calls` 或非默认 key 顺序的 chat 请求，body 里**不含**手机号；
- 在上游侧抓包确认收到的 body 与客户端发的 body **byte-for-byte 一致**（含原始 key 顺序、空白、`ensure_ascii=false` 等）；
- 若 body 中含手机号，则上游收到的应是脱敏后 `138****5678` 格式（此时允许 SafetyHub 重序列化后字节布局变化）。

---

## 九、真实上游联调须知

### 9.1 上游地址

当前本地联调地址：

```text
UPSTREAM_URL=https://yxai-api.nanfu.com
```

### 9.2 Token 安全

禁止：

- 把真实 token 写入 `.env.example`；
- 把真实 token 写入 Markdown 文档；
- 把真实 token 写入测试代码；
- 把真实 token 直接拼进会被记录的命令；
- 把真实 token 提交到 Git。

推荐：

- 手动输入 token；
- 使用只在当前 shell 生命周期存在的环境变量；
- 使用云平台 Secret Manager；
- 测试完成后立即清理 shell 历史和临时变量。

### 9.3 Windows 手动安全输入 token

```powershell
$secureToken = Read-Host -AsSecureString "Input upstream token"
$tokenPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPtr)
    $body = '{"model":"gpt-test","messages":[{"role":"user","content":"hello"}]}'
    Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/chat/completions -Method Post -ContentType "application/json; charset=utf-8" -Headers @{Authorization="Bearer $token"} -Body $body
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPtr)
}
```

### 9.4 Linux 手动安全输入 token

```bash
read -rsp "Input upstream token: " TOKEN
printf '\n'
curl -sS http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"model":"gpt-test","messages":[{"role":"user","content":"hello"}]}'
unset TOKEN
```

---

## 十、测试数据规范

| 类型 | 推荐做法 | 禁止做法 |
|------|----------|----------|
| API Key | 使用占位值或临时测试 token | 使用生产长期 token |
| 中文敏感词 | Windows 下用 Unicode 转义或 UTF-8 文件 | 直接在不确定编码的命令行中写中文 |
| 手机号/身份证 | 使用测试号码 | 使用真实个人信息 |
| 上游返回 | 记录状态码和结构 | 记录完整敏感响应内容 |
| 日志 | 记录 request_id、状态码、规则 ID | 记录 prompt 原文、Authorization、完整 APIKey |

---

## 十一、故障排查

### 11.1 block 规则没有命中

优先排查：

1. 请求体是否被编码破坏。
2. `engine/rules_config.yaml` 是否存在且被 ready 检查识别。
3. 服务是否重启或执行了规则 reload。
4. 规则是否 `enabled: true`。
5. 规则级别是否为 `block`。

### 11.2 正常请求没有到上游

优先排查：

1. `.env` 是否配置 `UPSTREAM_URL`。
2. 服务启动时是否读取了最新 `.env`。
3. 请求是否命中了 block 规则。
4. Header 是否包含 Authorization。
5. 上游地址是否包含重复 `/v1`。

当前实现中 `UPSTREAM_URL=https://yxai-api.nanfu.com` 会保留客户端请求路径自动拼接，例如 `/v1/chat/completions`、`/v1/embeddings`、`/v1/models`。

### 11.3 上游返回 401/403

说明请求大概率已触达上游，但 token 不合法或权限不足。检查：

- token 是否有效；
- token 是否过期；
- token 是否具备目标模型权限；
- Header 格式是否为 `Authorization: Bearer <token>`。

### 11.4 PowerShell 显示乱码

如果响应中文显示乱码，但 JSON 结构正确，可能只是终端显示编码问题。可通过以下方式减少影响：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

---

## 十二、阶段性验收清单

### 阶段 1 当前已完成能力

- [x] 健康检查通过。
- [x] 检测引擎测试通过。
- [x] 中继引擎测试通过。
- [x] block 请求返回伪装回复。
- [x] Chat 正常请求可触达真实上游。
- [x] OpenAI-compatible `/v1/*` 通用代理测试通过，覆盖 embeddings、models 和未知 JSON POST；非 Chat 接口默认透明透传。
- [x] Header 策略测试通过。
- [x] 上游路由测试通过。

### 阶段 2 当前已完成能力

- [x] 请求侧 desensitize 改写转发测试。
- [x] 阶段 2 弱规则集默认启用测试。
- [x] 规则定时热加载测试。
- [x] 后台规则启停测试。
- [x] 后台手动热加载测试。
- [x] block 请求返回伪装回复且不访问上游。
- [x] 普通 Chat 请求原样透传。
- [x] 非 Chat 接口默认透明透传。
- [ ] 真实 token 成功返回模型结果的受控联调记录。

### 阶段 3/6A 当前已完成能力

- [x] Chat passed 请求训练样本写入测试。
- [x] 文生图图片资产调度测试，确认响应引用提取和异步调度状态。
- [x] 文生图图片本体异步归档测试，覆盖 b64_json 解码保存、URL 下载状态记录和失败降级。
- [x] 图片资产状态 API 鉴权测试。
- [x] 训练样本/审计/图片资产失败降级测试。
- [x] Chat 流式响应训练样本提取测试。
- [x] 基础审计事件测试。
- [x] R1~R9 schema 预留测试。
- [x] Header 可选上游 Key 替换分支测试。
- [x] 管理 API Basic Auth + IP 白名单测试。

### 阶段 5 当前已完成能力

- [x] APIKey K-Sync 创建测试。
- [x] APIKey 哈希与加密存储测试。
- [x] 后台 APIKey 创建、列表、详情、更新、吊销和删除已吊销 Key 测试。
- [x] 单条替换上游 Key 测试。
- [x] CSV 批量替换解析与执行测试。
- [x] `/v1/*` 上游 Key 替换转发测试。
- [x] APIKey schema、后台表单和 API 响应不包含模型/能力 allowlist 字段，资源权限交由中转站判定测试。
- [x] APIKey 管理员操作审计测试。
- [x] Key 明文不在后台 API 响应中返回测试。

### 阶段 6A 生产稳定性当前待完成能力

- [x] APIKey SQLite 到 PostgreSQL 迁移验证，`api_keys: sqlite=23 postgres=23 OK`。
- [x] Linux 开发运行脚本连接 PostgreSQL 后 `/health/ready` 返回 `database=true` 和 `rules=true`。
- [x] Docker 生产启动不包含 `--reload`，Dockerfile 使用 `--workers ${UVICORN_WORKERS:-4}`。
- [x] `/v1/*` 全局有界并发队列测试覆盖正常进入、排队、队列满和排队超时；默认 4 worker 下容器总 `1000` in-flight + `2000` 排队目标仍需生产压测验证。
- [x] `/admin/*`、`/admin/api/*`、`/health/*` 不进入 `/v1/*` 队列。
- [ ] `/admin/api/stats` 短缓存测试覆盖缓存命中和过期刷新。
- [ ] 上游共享连接池测试覆盖配置传递和 client 生命周期关闭。
- [ ] 归档/审计后台队列测试覆盖入队、批量消费、队列满降级和 shutdown drain。
- [ ] 高并发压测报告记录 worker、队列、连接池、数据库、p95/p99、错误率和后台可用性。

### 阶段 8 长期规划测试

阶段 8 暂不开发，以下测试仅作为长期规划保留，不纳入本次生产上线阻塞项。

- [ ] 图片资产后台预览/下载页面测试，覆盖鉴权、操作审计和未授权拒绝。
- [ ] 图片资产存储配额、保留天数和清理任务测试。

---

## 十三、每次开发完成后的固定动作

1. 运行编译检查。
2. 运行全量测试。
3. 根据变更运行专项验证脚本。
4. 如果涉及中文规则，必须验证编码未损坏。
5. 如果涉及上游，必须确认 token 没有进入日志、文档、代码和命令历史。
6. 更新 `产品研发控制/SafetyHub当前开发进展和下一步规划.md`。
7. 必要时更新 `交付运行手册/`。
