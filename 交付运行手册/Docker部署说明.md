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

| 路径/配置 | 说明 |
|------|------|
| `SAFETYHUB_DATA_DIR` | 宿主机数据持久化目录，生产环境建议指向数据盘，例如 `/data/safetyhub/data` |
| `/app/data` | 容器内数据目录，由 Compose 挂载到 `SAFETYHUB_DATA_DIR` |
| `./data` | 未设置 `SAFETYHUB_DATA_DIR` 时的默认本地持久化目录 |
| `DB_URL` | SQLite 数据库连接，默认 `sqlite+aiosqlite:///./data/safetyhub.db` |
| `IMAGE_ASSET_DIR` | 图片资产目录，默认 `data/image_assets`，容器内对应 `/app/data/image_assets` |
| `SAFETYHUB_RULES_CONFIG` | 宿主机规则配置文件，生产环境建议指向数据盘，例如 `/data/safetyhub/config/rules_config.yaml` |
| `RULES_CONFIG_PATH` | 容器内规则配置路径，默认 `engine/rules_config.yaml` |
| `./admin/static` | Nginx 挂载的管理后台静态文件 |
| `./nginx/nginx.conf` | Nginx 配置 |
| `./.env` | Compose 注入的环境变量 |

生产服务器如果采用系统盘 + 数据盘，建议将数据盘挂载到固定路径，并在 `.env` 中设置：

```bash
SAFETYHUB_DATA_DIR=/data/safetyhub/data
SAFETYHUB_RULES_CONFIG=/data/safetyhub/config/rules_config.yaml
DB_URL=sqlite+aiosqlite:///./data/safetyhub.db
RULES_CONFIG_PATH=engine/rules_config.yaml
IMAGE_ASSET_DIR=data/image_assets
```

这样 SQLite 数据库和图片资产都会落在宿主机数据盘的 `/data/safetyhub/data` 下，规则配置文件会落在 `/data/safetyhub/config/rules_config.yaml`。容器重建、镜像升级或系统盘项目目录变更时，业务数据和后台修改过的规则都不会丢失。

首次部署前建议把项目内默认规则复制到数据盘配置目录：

```bash
mkdir -p /data/safetyhub/config /data/safetyhub/data
cp engine/rules_config.yaml /data/safetyhub/config/rules_config.yaml
```

`data/image_assets/{request_id}/` 不需要单独挂载；它是 `IMAGE_ASSET_DIR` 下按请求 ID 自动创建的子目录，已经包含在 `SAFETYHUB_DATA_DIR` 对应的数据盘挂载中。

---

## 七、生产注意事项

- 当前 Compose 暴露 `8000` 和 `8080`，生产环境可只暴露 Nginx 端口。
- TLS、证书续签、防火墙、备份和监控属于阶段 3 部署加固范围。
- 生产环境不要提交 `.env`、数据库文件和证书目录。
- 当前项目处于阶段 0，Docker 部署主要验证基础服务可启动。
