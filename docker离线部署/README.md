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
├── systemd/                      # docker / containerd 的 systemd 单元
│   ├── docker.service
│   ├── docker.socket
│   └── containerd.service
└── scripts/
    ├── prepare-offline-package.sh   # 在“联网机器”上执行: 拉取依赖 + 打包
    ├── install.sh                   # 在“内网离线服务器”上执行: 安装 + 部署
    └── uninstall.sh                 # 卸载 docker
```

## 步骤 1：在联网机器准备离线包

> 前置：已经按 `NF-SafetyHub/交付运行手册/build_intranet_offline_bundle.sh`
> 生成 `safetyhub_intranet_bundle_<ts>.tar.gz`。

```bash
cd /var/www/docker离线部署
bash scripts/prepare-offline-package.sh
```

脚本会：

1. 下载 Docker Engine 静态二进制（默认 `27.3.1`，`x86_64`）。
2. 下载 docker compose v2 二进制（默认 `v2.29.7`）。
3. 复制 `NF-SafetyHub/内网离线部署包/` 下最新的 `safetyhub_intranet_bundle_*.tar.gz`。
4. 在 **本目录的上一级**（即 `/var/www/`）下生成
   `docker-offline-deploy_<ts>.tar.gz` + `.sha256`，避免 tar 边写边读。

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

将 `docker-offline-deploy_<ts>.tar.gz` 与同名 `.sha256` 拷贝到目标服务器，校验后解压：

```bash
sha256sum -c docker-offline-deploy_<ts>.tar.gz.sha256
tar -xzf docker-offline-deploy_<ts>.tar.gz
cd docker离线部署
```

## 步骤 3：确认公网网关转发

本包按公网网关 HTTPS 终止模式部署：

```text
外网用户 -> https://llm-safetyhub.nanfu.com -> 运维公网网关/负载均衡 -> http://192.168.1.47:80 -> SafetyHub
```

服务器本机不保存 HTTPS 证书，也不直接处理 TLS。请运维确认：

- `llm-safetyhub.nanfu.com` 公网 DNS 指向公网网关/负载均衡
- 网关/负载均衡上配置 `llm-safetyhub.nanfu.com` 的 HTTPS 证书
- 网关后端转发目标为 `http://192.168.1.47:80`
- 网关到后端服务器 TCP `80` 已放通

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
   调用其内置 `install.sh`：`docker load` 镜像 → `docker compose up -d`。

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
