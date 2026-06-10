#!/usr/bin/env bash
# 卸载离线安装的 docker / containerd / compose plugin。
# 注意: 不会删除 /var/lib/docker, 如需彻底清理请手动 rm -rf。
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请使用 root 或 sudo 运行" >&2
  exit 1
fi

systemctl disable --now docker.service docker.socket containerd.service 2>/dev/null || true
rm -f /etc/systemd/system/docker.service \
      /etc/systemd/system/docker.socket \
      /etc/systemd/system/containerd.service
systemctl daemon-reload

for bin in docker dockerd docker-init docker-proxy containerd containerd-shim \
           containerd-shim-runc-v2 ctr runc docker-compose; do
  rm -f "/usr/local/bin/${bin}"
done
rm -f /usr/local/lib/docker/cli-plugins/docker-compose
rmdir /usr/local/lib/docker/cli-plugins 2>/dev/null || true
rmdir /usr/local/lib/docker 2>/dev/null || true

echo "[uninstall] 已移除 docker 二进制与 systemd 单元"
echo "[uninstall] 如需删除数据请手动: rm -rf /var/lib/docker /var/lib/containerd"
