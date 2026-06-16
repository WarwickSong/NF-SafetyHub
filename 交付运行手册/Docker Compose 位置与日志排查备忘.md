# Docker Compose 位置与日志排查备忘

## 适用场景

用于排查 SafetyHub Docker 部署后出现的请求异常、SSE 流式异常、Trae/OpenClaw 连接异常、Nginx 反代异常等问题。

当前 Docker 离线部署后，应用通常位于类似路径：

```bash
/opt/docker离线部署/app-bundle/_extracted/safetyhub_intranet_bundle_YYYYMMDD_HHMMSS/NF-SafetyHub
```

该目录下应包含：

```bash
docker-compose.yml
nginx/nginx.conf
交付运行手册/deploy_intranet_docker.sh
.env
```

## 一、定位 Docker Compose 工作目录

如果知道当前部署目录，直接进入：

```bash
cd /opt/docker离线部署/app-bundle/_extracted/safetyhub_intranet_bundle_YYYYMMDD_HHMMSS/NF-SafetyHub
cd /opt/docker离线部署/app-bundle/_extracted/*/NF-SafetyHub
```

如果忘记目录，可以通过容器反查 Compose 工作目录：

```bash
docker inspect safetyhub-nginx \
  --format '{{ index .Config.Labels "com.docker.compose.project.working_dir"}}'
```

查看 Compose 文件路径：

```bash
docker inspect safetyhub-nginx \
  --format '{{ index .Config.Labels "com.docker.compose.project.config_files"}}'
```

如果容器名不确定，先列出容器：

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
```

也可以全盘搜索 Compose 文件：

```bash
find / -name 'docker-compose*.yml' -o -name 'compose*.yml' 2>/dev/null
```

## 二、查看容器状态

进入 Compose 工作目录后执行：

```bash
docker compose ps
```

正常应看到：

```text
safetyhub-app        Up ... healthy
safetyhub-nginx      Up ... 0.0.0.0:80->80/tcp
safetyhub-postgres   Up ... healthy
```

如果不在 Compose 工作目录，也可以直接看容器：

```bash
docker ps | grep safetyhub
```

## 三、查看日志

查看最近 200 行应用日志：

```bash
docker compose logs --tail=200 safetyhub
```

查看最近 200 行 Nginx 日志：

```bash
docker compose logs --tail=200 nginx
```

实时跟踪应用和 Nginx 日志：

```bash
docker compose logs -f safetyhub nginx
```

不依赖 Compose 工作目录时，可以直接按容器名查看：

```bash
docker logs --tail=200 safetyhub-app
docker logs --tail=200 safetyhub-nginx
docker logs -f safetyhub-app safetyhub-nginx
```

## 四、不要看错日志位置

Docker 部署的 Nginx 日志通常不会出现在宿主机：

```bash
/var/log/nginx/access.log
/var/log/nginx/error.log
```

如果执行下面命令提示不存在，是正常的：

```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

因为当前 Nginx 运行在容器里，日志输出到 Docker stdout/stderr，应使用：

```bash
docker compose logs -f nginx
```

或：

```bash
docker logs -f safetyhub-nginx
```

## 五、排查 Trae/OpenClaw 连接异常

实时打开日志：

```bash
docker compose logs -f safetyhub nginx
```

然后在 Trae/OpenClaw 里重新发起一次请求。

重点观察 Nginx 日志中的：

```text
POST /v1/chat/completions
status
request_time
upstream_response_time
content_length
request_length
User-Agent
```

常见判断：

| 现象 | 含义 |
| --- | --- |
| `200` 且响应大小正常 | 容器内 Nginx 和应用基本正常 |
| `408` 且 `urt=-` | 请求还没转到应用，Nginx 在等待客户端请求体时超时 |
| `408` 且 `rl` 明显小于 `cl` | 客户端声明了较大的 `Content-Length`，但实际只发送了部分请求体 |
| `499` | 客户端主动断开连接 |
| `502` | Nginx 连接后端应用失败或后端提前关闭 |
| 应用日志出现 `ClientDisconnect` | 应用读取请求体时客户端已经断开 |
| Python 脚本正常，Trae/OpenClaw 异常 | 通常是客户端请求形态、连接复用、外层网关策略差异 |

## 六、快速过滤关键日志

过滤 Nginx 中的 `/v1/chat/completions`：

```bash
docker compose logs nginx | grep '/v1/chat/completions'
```

过滤异常状态：

```bash
docker compose logs nginx | grep -E ' 408 | 499 | 500 | 502 | 504 '
```

过滤应用断连异常：

```bash
docker compose logs safetyhub | grep -i 'ClientDisconnect\|disconnect\|traceback\|exception'
```

过滤 Trae/OpenClaw 相关 User-Agent：

```bash
docker compose logs nginx | grep -Ei 'trae|openclaw|hertz|reqwest|hyper'
```

## 七、验证服务是否正常

健康检查：

```bash
curl -i http://127.0.0.1/health/ready
```

如果 `.env` 中 `SAFETYHUB_HTTP_PORT` 不是 80，则替换端口：

```bash
curl -i http://127.0.0.1:${SAFETYHUB_HTTP_PORT}/health/ready
```

本机验证管理后台：

```bash
curl -I http://127.0.0.1/admin/
```

验证流式接口建议使用项目里的测试脚本或专门的 SSE 验证脚本，重点确认响应头：

```text
Content-Type: text/event-stream
Transfer-Encoding: chunked
Content-Encoding: None
X-Accel-Buffering: no
```

## 八、重新部署后确认配置生效

进入 Compose 工作目录后：

```bash
docker compose exec nginx nginx -T | grep -E 'proxy_buffering|proxy_request_buffering|X-Accel-Buffering|log_format|client_max_body_size|client_body_buffer_size|client_body_timeout'
```

查看容器内 Nginx 完整配置：

```bash
docker compose exec nginx nginx -T
```

重启 Nginx：

```bash
docker compose restart nginx
```

重启应用和 Nginx：

```bash
docker compose restart safetyhub nginx
```

## 九、Trae/OpenClaw 408 判读

如果日志类似：

```text
POST /v1/chat/completions HTTP/1.1" 408 0 rt=120.013 urt=- cl=51599 rl=16384 ua="hertz"
```

含义是：

- `cl=51599`：客户端声明请求体约 51KB。
- `rl=16384`：Nginx 实际只收到约 16KB 请求数据。
- `urt=-`：请求没有转发到 SafetyHub 应用。
- `rt=120.013`：Nginx 等待请求体 120 秒后超时。
- `ua="hertz"`：请求来自 Trae/OpenClaw 使用的客户端栈。

这种情况下问题发生在“客户端到 Docker Nginx 的请求体发送阶段”，不是 FastAPI 处理阶段，也不是 SSE 响应返回阶段。

对应处理原则：

```nginx
location /v1/ {
    proxy_buffering off;
    proxy_request_buffering off;
    client_body_timeout 300s;
}
```

`proxy_request_buffering off` 会让 Nginx 不再等待完整请求体落盘后才转发，而是更接近 `run_prod.sh` 直连 Uvicorn 的行为。

多模态和长上下文请求建议同时确认：

```nginx
client_max_body_size 100m;
client_body_buffer_size 8m;
```

- `client_max_body_size` 是允许的最大请求体大小，图片 base64、长上下文、工具调用参数都会计入。
- `client_body_buffer_size` 是 Nginx 尽量放在内存里的请求体缓冲，不是越大越好，过大会按并发放大内存占用。
- 如果未来需要传更大的原始文件，不建议继续无限增大 JSON 请求体，应优先走文件上传/对象存储/引用 URL 方案。

## 十、CDN/外层网关处理

如果内网服务器前面新增了 CDN、WAF、API 网关、负载均衡或公网 Nginx，且日志中反复出现：

```text
408 rt=300.xxx cl=50xxx rl=16384 ua="hertz"
```

应优先怀疑外层入口没有完整转发请求体。`rl=16384` 是 16KB 边界，常见于 CDN/WAF/代理对请求体分片、缓冲、审查或转发策略不兼容。

建议让运维对 `/v1/` 路径单独配置：

- 关闭 CDN 缓存、页面优化、智能压缩、Brotli、Gzip。
- 关闭 WAF 请求体审查、Bot 防护、API 安全扫描，或把 `/v1/chat/completions` 加白。
- 关闭请求体大小/分片限制，确认允许至少 `100MB` 请求体。
- 禁用请求体缓冲/聚合策略，确保大 POST body 能持续转发到源站。
- 延长源站读写超时到至少 `300s`。
- 对 SSE 响应关闭响应缓冲，保留 `text/event-stream` 和 `Transfer-Encoding: chunked`。
- 如果 CDN 不支持稳定代理 SSE + 大 POST body，应让 `/v1/` 走 DNS 直连源站或单独 API 域名，不经过 CDN。

推荐的临时验证方式：

```bash
curl --resolve llm-safetyhub.nanfu.com:443:源站公网IP https://llm-safetyhub.nanfu.com/health/ready -i
```

如果绕过 CDN 后 Trae/OpenClaw 正常，问题就在 CDN/外层网关；如果绕过 CDN 仍异常，再继续看 Docker Nginx 和应用日志。

## 十一、关键结论

- Docker 部署不要优先看宿主机 `/var/log/nginx/*.log`，应看 `docker compose logs nginx`。
- `run_prod.sh` 正常但 Docker 异常时，优先看 Docker Nginx 日志和 SafetyHub 应用日志。
- SSE 响应流要关闭响应缓冲：`proxy_buffering off`。
- Trae/OpenClaw 如果出现 `408`、`rt=300.xxx`、`rl=16384`、`cl≈50KB`，且近期新增 CDN，应优先排查 CDN/WAF/外层网关是否截断或缓冲请求体。
- Trae/OpenClaw 如果出现 `408`、`urt=-`、`rl` 明显小于 `cl`，说明请求体没有完整进入 Nginx，应让 `/v1/` 使用 `proxy_request_buffering off` 更接近直连行为。
- 如果看到 `499` 或 `ClientDisconnect`，重点排查客户端/外层网关是否主动断开请求。
