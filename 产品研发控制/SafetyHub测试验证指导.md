# LLM-SafetyHub 测试验证指导

> 本文档定义 SafetyHub 在 Windows、Linux、Docker 和真实上游联调场景下的测试方法、注意事项和验收标准。  
> 当前重点覆盖阶段 0 基础设施、阶段 1 检测引擎和阶段 1 中继引擎。后续消息归档、审计告警、管理后台完成后应继续扩展本文档。

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

```powershell
cd d:\Code\public\NF-SafetyHub
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

当前基线：

```text
25 passed
```

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

```bash
cd /opt/NF-SafetyHub
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
```

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

### 5.2 启动

```bash
docker compose up --build -d
```

### 5.3 验证

```bash
docker compose ps
curl http://127.0.0.1:8080/health/live
curl http://127.0.0.1:8080/health/ready
```

---

## 六、检测引擎验证

### 6.1 规则数量验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_rules_config.py
```

当前要求：

| 规则类型 | 最低数量 |
|----------|----------|
| 关键词规则 | 20 |
| 正则规则 | 10 |

### 6.2 关键词 block 验证

Windows PowerShell 推荐使用 JSON Unicode 转义，避免中文编码损坏：

```powershell
$body = '{"model":"gpt-test","messages":[{"role":"user","content":"\u8bf7\u5e2e\u6211\u5916\u53d1\u4ea7\u54c1\u8def\u7ebf\u56fe"}]}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/chat/completions -Method Post -ContentType "application/json; charset=utf-8" -Headers @{Authorization="Bearer placeholder-token"} -Body $body
```

预期：

- 返回 `chatcmpl-safetyhub-*`。
- 不出现上游认证错误。
- 响应结构兼容 OpenAI Chat Completions。

### 6.3 编码验证

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

## 七、中继引擎验证

### 7.1 单元/集成测试

```powershell
.\交付运行手册\verify_relay.ps1
```

覆盖：

- 伪装回复格式；
- Header 剥离策略；
- 上游 URL 构造；
- block 拦截路径；
- 正常请求转发路径；
- 非法 JSON 请求。

### 7.2 本地 block 拦截验证

```powershell
$body = '{"model":"gpt-test","messages":[{"role":"user","content":"\u8bf7\u5e2e\u6211\u5916\u53d1\u4ea7\u54c1\u8def\u7ebf\u56fe"}]}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/chat/completions -Method Post -ContentType "application/json; charset=utf-8" -Headers @{Authorization="Bearer placeholder-token"} -Body $body
```

预期：本地返回伪装回复，不访问上游。

### 7.3 上游触达验证

使用占位 token：

```powershell
$body = '{"model":"gpt-test","messages":[{"role":"user","content":"hello"}]}'
Invoke-WebRequest -Uri http://127.0.0.1:8000/v1/chat/completions -Method Post -ContentType "application/json; charset=utf-8" -Headers @{Authorization="Bearer placeholder-token"} -Body $body
```

预期：返回上游 `401` 或 `403`，说明正常请求已触达真实上游。

---

## 八、真实上游联调须知

### 8.1 上游地址

当前本地联调地址：

```text
UPSTREAM_URL=https://yxai-api.nanfu.com
```

### 8.2 Token 安全

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

### 8.3 Windows 手动安全输入 token

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

### 8.4 Linux 手动安全输入 token

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

## 九、测试数据规范

| 类型 | 推荐做法 | 禁止做法 |
|------|----------|----------|
| API Key | 使用占位值或临时测试 token | 使用生产长期 token |
| 中文敏感词 | Windows 下用 Unicode 转义或 UTF-8 文件 | 直接在不确定编码的命令行中写中文 |
| 手机号/身份证 | 使用测试号码 | 使用真实个人信息 |
| 上游返回 | 记录状态码和结构 | 记录完整敏感响应内容 |
| 日志 | 记录 request_id、状态码、规则 ID | 记录 prompt 原文、Authorization、完整 APIKey |

---

## 十、故障排查

### 10.1 block 规则没有命中

优先排查：

1. 请求体是否被编码破坏。
2. `engine/rules_config.yaml` 是否存在且被 ready 检查识别。
3. 服务是否重启或执行了规则 reload。
4. 规则是否 `enabled: true`。
5. 规则级别是否为 `block`。

### 10.2 正常请求没有到上游

优先排查：

1. `.env` 是否配置 `UPSTREAM_URL`。
2. 服务启动时是否读取了最新 `.env`。
3. 请求是否命中了 block 规则。
4. Header 是否包含 Authorization。
5. 上游地址是否包含重复 `/v1`。

当前实现中 `UPSTREAM_URL=https://yxai-api.nanfu.com` 会自动拼接 `/v1/chat/completions`。

### 10.3 上游返回 401/403

说明请求大概率已触达上游，但 token 不合法或权限不足。检查：

- token 是否有效；
- token 是否过期；
- token 是否具备目标模型权限；
- Header 格式是否为 `Authorization: Bearer <token>`。

### 10.4 PowerShell 显示乱码

如果响应中文显示乱码，但 JSON 结构正确，可能只是终端显示编码问题。可通过以下方式减少影响：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

---

## 十一、阶段性验收清单

### 阶段 1 当前已完成能力

- [x] 健康检查通过。
- [x] 检测引擎测试通过。
- [x] 中继引擎测试通过。
- [x] block 请求返回伪装回复。
- [x] 正常请求可触达真实上游。
- [x] Header 策略测试通过。
- [x] 上游路由测试通过。

### 阶段 1 后续必须补充

- [ ] 消息归档写入测试。
- [ ] 归档失败降级测试。
- [ ] 流式响应归档测试。
- [ ] 基础审计事件测试。
- [ ] 规则定时热加载测试。
- [ ] 真实 token 成功返回模型结果的受控联调记录。

---

## 十二、每次开发完成后的固定动作

1. 运行编译检查。
2. 运行全量测试。
3. 根据变更运行专项验证脚本。
4. 如果涉及中文规则，必须验证编码未损坏。
5. 如果涉及上游，必须确认 token 没有进入日志、文档、代码和命令历史。
6. 更新 `产品研发控制/SafetyHub当前开发进展和下一步规划.md`。
7. 必要时更新 `交付运行手册/`。
