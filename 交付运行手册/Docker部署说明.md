# LLM-SafetyHub Docker 部署说明

> Docker 部署使用项目根目录已有 `Dockerfile`、`docker-compose.yml` 和 `nginx/nginx.conf`。

---

## 一、适用场景

- 本地模拟生产运行。
- 测试环境部署。
- 后续生产环境标准化部署。

---

## 二、准备环境

进入项目根目录：

```powershell
cd d:\Code\public\NF-SafetyHub
```

创建 `.env`：

```powershell
Copy-Item .\项目部署\.env.production.example .\.env
notepad .\.env
```

至少修改：

| 配置项 | 要求 |
|--------|------|
| `ENVIRONMENT` | 生产部署使用 `production` |
| `DEBUG` | 生产部署使用 `false` |
| `UPSTREAM_URL` | 改为真实上游中转站地址 |
| `ADMIN_PASSWORD` | 改为强密码，至少 12 位 |
| `WEBHOOK_URL` | 如需告警，改为真实 Webhook 地址 |

---

## 三、启动服务

```powershell
.\项目部署\deploy_docker.ps1
```

脚本会执行：

```powershell
docker compose up --build -d
```

---

## 四、访问地址

| 服务 | 地址 |
|------|------|
| FastAPI 健康检查 | `http://127.0.0.1:8000/health/live` |
| Nginx 健康检查 | `http://127.0.0.1:8080/health/live` |
| 管理后台占位页 | `http://127.0.0.1:8080/admin/` |

---

## 五、常用命令

查看容器：

```powershell
docker compose ps
```

查看日志：

```powershell
docker compose logs -f safetyhub
```

停止服务：

```powershell
docker compose down
```

重新构建：

```powershell
docker compose up --build -d
```

---

## 六、数据与配置

| 路径 | 说明 |
|------|------|
| `./data` | SQLite 数据库持久化目录 |
| `./admin/static` | Nginx 挂载的管理后台静态文件 |
| `./nginx/nginx.conf` | Nginx 配置 |
| `./.env` | Compose 注入的环境变量 |

---

## 七、生产注意事项

- 当前 Compose 暴露 `8000` 和 `8080`，生产环境可只暴露 Nginx 端口。
- TLS、证书续签、防火墙、备份和监控属于阶段 3 部署加固范围。
- 生产环境不要提交 `.env`、数据库文件和证书目录。
- 当前项目处于阶段 0，Docker 部署主要验证基础服务可启动。
