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
| `408` | 客户端请求体发送超时，常见于客户端/外层网关提前断开 |
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
docker compose exec nginx nginx -T | grep -E 'proxy_buffering|proxy_request_buffering|X-Accel-Buffering|log_format|client_body_timeout'
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

## 九、关键结论

- Docker 部署不要优先看宿主机 `/var/log/nginx/*.log`，应看 `docker compose logs nginx`。
- `run_prod.sh` 正常但 Docker 异常时，优先看 Docker Nginx 日志和 SafetyHub 应用日志。
- SSE 响应流要关闭响应缓冲：`proxy_buffering off`。
- 请求体不属于 SSE 响应流，通常应保持 `proxy_request_buffering on`，让 Nginx 完整接收请求体后再转给应用。
- 如果看到 `408` 或 `ClientDisconnect`，重点排查客户端/外层网关是否提前断开请求。
