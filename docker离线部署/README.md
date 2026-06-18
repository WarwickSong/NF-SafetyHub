# NF-SafetyHub 离线 Docker 部署包

本目录用于在**完全离线**的内网服务器上部署 `NF-SafetyHub` 系统。
目标服务器无需预装 docker / docker compose，本包内置静态二进制 + systemd 单元，
通过 `scripts/install.sh` 一键完成安装。

## 目录结构

```
docker离线部署/
├── README.md
├── docker/                       # docker / compose 离线二进制（由 prepare 脚本生成）
│   ├── docker-<ver>.tgz
│   ├── docker-compose-linux-<arch>
│   ├── VERSIONS.txt
│   └── SHA256SUMS
├── app-bundle/                   # NF-SafetyHub 镜像 bundle（含 postgres / nginx / safetyhub）
│   └── safetyhub_intranet_bundle_<ts>.tar.gz
├── 部署文件/                      # 最终交付产物的默认输出目录（git 仅保留 .gitignore 与 *.sha256）
│   ├── docker-offline-deploy_<ts>.tar.gz
│   └── docker-offline-deploy_<ts>.tar.gz.sha256
├── systemd/                      # docker / containerd 的 systemd 单元
│   ├── docker.service
│   ├── docker.socket
│   └── containerd.service
└── scripts/
    ├── prepare-offline-package.sh   # 在“联网机器”上执行: 拉取依赖 + 打包到 部署文件/
    ├── install.sh                   # 在“内网离线服务器”上执行: 安装 + 部署
    └── uninstall.sh                 # 卸载 docker
```

## 步骤 1：在联网机器准备离线包

> 前置：已经按 `NF-SafetyHub/交付运行手册/build_intranet_offline_bundle.sh`
> 生成 `safetyhub_intranet_bundle_<ts>.tar.gz`。

```bash
# 进入仓库内的 docker离线部署 目录（路径相对于你当前 clone 的位置即可，不必固定在 /var/www）
cd <仓库根>/docker离线部署
bash scripts/prepare-offline-package.sh
```

脚本会：

1. 下载 Docker Engine 静态二进制（默认 `27.3.1`，`x86_64`）。
2. 下载 docker compose v2 二进制（默认 `v2.29.7`）。
3. 复制仓库 `内网离线部署包/` 下最新的 `safetyhub_intranet_bundle_*.tar.gz`。
4. 在 `docker离线部署/部署文件/` 下生成
   `docker-offline-deploy_<ts>.tar.gz` + `.sha256`，作为正式交付产物。
   打包时会自动 `--exclude` 掉 `部署文件/`，避免把刚生成的包再打进去。

> 默认路径全部基于脚本所在的 `docker离线部署/` 目录推导，不依赖任何绝对路径，
> 仓库迁移到任意位置都能直接运行。如需自定义，可通过环境变量覆盖：
>
> ```bash
> # 自定义最终交付产物目录（绝对路径或相对于当前 cwd）
> PKG_OUTPUT_DIR=/tmp/safetyhub-out bash scripts/prepare-offline-package.sh
>
> # 把 docker离线部署/ 单独拷出来运行时，需要显式指向真正的 NF-SafetyHub 仓库根
> NF_PROJECT_ROOT=/path/to/NF-SafetyHub bash scripts/prepare-offline-package.sh
> ```

默认下载源（已实测可用，全部是国内镜像/代理）：

- Docker Engine: 阿里云 / 清华 / 南大 / docker 官方 依次回退
- docker compose: `gh-proxy.com` / `ghfast.top` / GitHub 官方 依次回退

如需切换版本/架构或自定义源：

```bash
DOCKER_VERSION=27.3.1 ARCH=aarch64 COMPOSE_ARCH=aarch64 \
  bash scripts/prepare-offline-package.sh

# 或者完全自定义下载源（空格分隔的多个 URL）
DOCKER_URLS="https://your.mirror/docker-27.3.1.tgz" \
COMPOSE_URLS="https://your.mirror/docker-compose-linux-x86_64" \
  bash scripts/prepare-offline-package.sh
```

> 网络受限时，也可以**手动**把 `docker-<ver>.tgz` 与
> `docker-compose-linux-<arch>` 放到 `docker/` 目录下，脚本会自动跳过下载。

## 步骤 2：拷贝到内网服务器

将 `部署文件/` 下的 `docker-offline-deploy_<ts>.tar.gz` 与同名 `.sha256` 拷贝到目标服务器，
校验后解压：

```bash
sha256sum -c docker-offline-deploy_<ts>.tar.gz.sha256
tar -xzf docker-offline-deploy_<ts>.tar.gz
cd docker离线部署
```

## 步骤 3：准备公网网关 HTTPS 转发

管理后台启用了 `Secure` Cookie，浏览器必须通过 HTTPS 访问公网域名，
但**业务服务器不处理 HTTPS 证书**。证书部署在上游公网网关/负载均衡，
本包内 nginx 容器只监听 HTTP 80。

```text
外网用户 -> https://llm-safetyhub.nanfu.com -> 公网网关/负载均衡（HTTPS 终止）
        -> http://内网节点:80 -> SafetyHub
```

公网网关需要在反向代理时保留 `Host`，并强制注入：

```text
X-Forwarded-Proto: https
```

容器内 uvicorn 已启用 `--proxy-headers`，会基于该头识别公网请求为 HTTPS，
从而让 Secure Cookie 在浏览器侧正常落地。

运维侧建议配置：

```text
Frontend: https://llm-safetyhub.nanfu.com:443
Backend:  http://<内网节点>:80
Health:   GET http://<内网节点>/health/ready
```

> 注意：不要把后端配置成 `https://<内网节点>`，后端必须是 HTTP 80。
> 本包不需要在业务服务器准备 `safetyhub.crt` / `safetyhub.key`。

## 步骤 4：执行一键安装

```bash
sudo bash scripts/install.sh
```

脚本会：

1. 解压 docker 静态二进制到 `/usr/local/bin/`。
2. 安装 compose v2 到 `/usr/local/lib/docker/cli-plugins/docker-compose`，
   并在 `/usr/local/bin/docker-compose` 留软链接。
3. 注册并启动 `containerd.service` / `docker.socket` / `docker.service`。
4. 解压 `app-bundle/safetyhub_intranet_bundle_*.tar.gz` 到 `app-bundle/_extracted/`，
   调用其内置 `install.sh`：`docker load` 镜像 → 启动 PostgreSQL → 保留 `api_keys` 表并重建其他业务表 → 启动 SafetyHub/Nginx。

可选环境变量：

| 变量 | 说明 |
| --- | --- |
| `SKIP_DOCKER_INSTALL=true` | 目标机器已装 docker，仅部署应用 |
| `SKIP_APP_DEPLOY=true`     | 仅安装 docker，不启动应用 |
| `SAFETYHUB_BUNDLE=/path/to/xxx.tar.gz` | 指定使用的 SafetyHub bundle |

安装完成后在服务器本机验证后端：

```bash
curl http://127.0.0.1/health/ready
```

运维网关配置完成后，从公网验证：

```bash
curl -I https://llm-safetyhub.nanfu.com/health/ready
```

浏览器访问：

```text
https://llm-safetyhub.nanfu.com/admin/
```

## 升级 / 替换旧版本（迭代新版本时使用）

当目标机器上已经跑过一版 SafetyHub（容器名形如 `safetyhub-nginx` /
`safetyhub-app` / `safetyhub-postgres`），想换成新版本时，按以下顺序操作：

### 1. 定位旧 compose 工作目录

```bash
docker inspect safetyhub-nginx \
  --format '{{ index .Config.Labels "com.docker.compose.project.working_dir"}}'

docker inspect safetyhub-nginx \
  --format '{{ index .Config.Labels "com.docker.compose.project.config_files"}}'
```

如果忘了旧 compose 文件位置，也可以全盘搜：

```bash
find / -name 'docker-compose*.y*ml' 2>/dev/null
```

### 2. 停掉并删除旧容器

进入上一步得到的目录执行：

```bash
cd <旧 compose 工作目录>
docker compose down
```

如果 `docker compose down` 提示 `no configuration file provided: not found`，
说明当前目录没有 compose 文件，按容器名直接停删即可：

```bash
docker stop safetyhub-nginx safetyhub-app safetyhub-postgres
docker rm   safetyhub-nginx safetyhub-app safetyhub-postgres
```

> 注意：**不要**执行 `docker volume prune` / `rm -rf /var/lib/docker`，
> 否则 postgres 数据会丢。如需保留旧数据，先确认数据卷：
>
> ```bash
> docker volume ls | grep -i safetyhub
> ```

### 3. 确认端口已释放

新栈只占用业务服务器的 80 端口，443 由上游网关/负载均衡处理：

```bash
docker ps
ss -lntp | grep ':80 '
```

如果旧版本 `safetyhub-nginx` 一直 `Restarting`，并且日志出现：

```text
cannot load certificate "/etc/nginx/certs/safetyhub.crt"
```

说明旧包仍包含 443 证书配置。直接按上面的 `docker compose down` 或 `docker stop/rm`
删除旧容器后，用新包重新部署即可；业务服务器不需要补证书。

### 4. 部署新版本

旧 docker 引擎可继续复用，跳过 docker 安装步骤：

```bash
cd <新版> docker离线部署
sudo SKIP_DOCKER_INSTALL=true bash scripts/install.sh
```

如需同时升级 docker 引擎本身，先 `sudo bash scripts/uninstall.sh`，
再正常 `sudo bash scripts/install.sh`。

本次应用部署会保留内网 PostgreSQL 里的 `api_keys` 表，删除并重建其他 SafetyHub 业务表；不会从 JSON/SQL 重新导入 APIKey。执行前请确认应用包内 `NF-SafetyHub/.env` 的 `SAFETYHUB_POSTGRES_DATA_DIR`、`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`DB_URL` 指向旧内网数据库。

### 5. 验证

```bash
curl http://127.0.0.1/health/ready
docker ps
```

## 卸载

```bash
sudo bash scripts/uninstall.sh
```

仅移除 docker 二进制与 systemd 单元，不会删除 `/var/lib/docker` 数据，
如需彻底清理请手动 `rm -rf /var/lib/docker /var/lib/containerd`。

## 常见问题

- **dockerd 启动失败 / cgroup v1**：Ubuntu 22.04+ / RHEL 9 默认 cgroup v2 可直接使用。
  老系统如 CentOS 7 需开启 cgroup v2 或改用包管理器版本的 docker。
- **selinux**：RHEL 系如开启 selinux，需要 `setenforce 0` 或自行配置策略。
- **iptables**：dockerd 依赖 `iptables`，目标机器需保留该命令。
