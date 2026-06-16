#!/usr/bin/env bash
# 在“离线内网服务器”上执行，自动完成:
#   1) 安装 Docker Engine + CLI + containerd + docker compose v2 (仅二进制)
#   2) 注册 systemd 服务并启动 dockerd
#   3) 加载 NF-SafetyHub 镜像 bundle 并通过 docker compose 拉起服务
#
# 用法:
#   sudo bash scripts/install.sh
#
# 可选环境变量:
#   SAFETYHUB_BUNDLE   指定使用的 safetyhub_intranet_bundle_*.tar.gz 路径
#   SKIP_DOCKER_INSTALL=true  目标机器已安装 docker, 仅做镜像加载与启动
#   SKIP_APP_DEPLOY=true      仅安装 docker, 不部署应用
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_DIR="${ROOT_DIR}/docker"
APP_BUNDLE_DIR="${ROOT_DIR}/app-bundle"
SYSTEMD_DIR="${ROOT_DIR}/systemd"

INSTALL_PREFIX="/usr/local/bin"
COMPOSE_PLUGIN_DIR="/usr/local/lib/docker/cli-plugins"

log() { printf '[install] %s\n' "$*"; }
err() { printf '[install][ERROR] %s\n' "$*" >&2; }

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    err "请使用 root 或 sudo 运行: sudo bash $0"
    exit 1
  fi
}

install_docker() {
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    log "检测到 docker 已可用, 跳过安装"
    return 0
  fi

  local docker_tgz
  docker_tgz="$(ls -1 "${DOCKER_DIR}"/docker-*.tgz 2>/dev/null | head -n1 || true)"
  if [ -z "${docker_tgz}" ] || [ ! -f "${docker_tgz}" ]; then
    err "未找到 ${DOCKER_DIR}/docker-*.tgz, 请先在联网机器运行 prepare-offline-package.sh"
    exit 1
  fi

  log "解压 ${docker_tgz} -> ${INSTALL_PREFIX}"
  tar -xzf "${docker_tgz}" -C /tmp
  install -m 0755 /tmp/docker/* "${INSTALL_PREFIX}/"
  rm -rf /tmp/docker

  log "安装 docker compose v2 plugin"
  local compose_bin
  compose_bin="$(ls -1 "${DOCKER_DIR}"/docker-compose-linux-* 2>/dev/null | head -n1 || true)"
  if [ -z "${compose_bin}" ] || [ ! -f "${compose_bin}" ]; then
    err "未找到 ${DOCKER_DIR}/docker-compose-linux-*"
    exit 1
  fi
  mkdir -p "${COMPOSE_PLUGIN_DIR}"
  install -m 0755 "${compose_bin}" "${COMPOSE_PLUGIN_DIR}/docker-compose"
  # 同时保留独立 docker-compose 命令, 兼容旧脚本
  ln -sf "${COMPOSE_PLUGIN_DIR}/docker-compose" "${INSTALL_PREFIX}/docker-compose"

  log "创建 docker 用户组"
  if ! getent group docker >/dev/null; then
    groupadd --system docker
  fi

  log "注册 systemd 单元"
  install -m 0644 "${SYSTEMD_DIR}/docker.service" /etc/systemd/system/docker.service
  install -m 0644 "${SYSTEMD_DIR}/docker.socket"  /etc/systemd/system/docker.socket
  install -m 0644 "${SYSTEMD_DIR}/containerd.service" /etc/systemd/system/containerd.service

  systemctl daemon-reload
  systemctl enable --now containerd.service
  systemctl enable --now docker.socket
  systemctl enable --now docker.service

  log "等待 docker daemon 就绪"
  for _ in $(seq 1 30); do
    if docker info >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  docker version
  docker compose version
}

deploy_app() {
  local bundle="${SAFETYHUB_BUNDLE:-}"
  if [ -z "${bundle}" ]; then
    bundle="$(ls -1t "${APP_BUNDLE_DIR}"/safetyhub_intranet_bundle_*.tar.gz 2>/dev/null | head -n1 || true)"
  fi
  if [ -z "${bundle}" ] || [ ! -f "${bundle}" ]; then
    err "未找到 SafetyHub 镜像 bundle, 请将 safetyhub_intranet_bundle_*.tar.gz 放到 ${APP_BUNDLE_DIR}/"
    exit 1
  fi

  log "校验 bundle 完整性"
  if [ -f "${bundle}.sha256" ]; then
    local expected_hash actual_hash
    expected_hash="$(awk 'NR==1 {print $1}' "${bundle}.sha256")"
    actual_hash="$(sha256sum "${bundle}" | awk '{print $1}')"
    if [ -z "${expected_hash}" ] || [ "${expected_hash}" != "${actual_hash}" ]; then
      err "bundle sha256 校验失败: ${bundle}"
      err "expected: ${expected_hash:-empty}"
      err "actual:   ${actual_hash}"
      exit 1
    fi
    log "bundle sha256 校验通过"
  else
    log "WARNING: 未提供 ${bundle}.sha256, 跳过 sha256 校验"
  fi

  local extract_dir="${ROOT_DIR}/app-bundle/_extracted"
  rm -rf "${extract_dir}"
  mkdir -p "${extract_dir}"

  log "解压 SafetyHub bundle -> ${extract_dir}"
  tar -xzf "${bundle}" -C "${extract_dir}"

  local inner_dir
  inner_dir="$(find "${extract_dir}" -maxdepth 1 -mindepth 1 -type d | head -n1)"
  if [ -z "${inner_dir}" ] || [ ! -f "${inner_dir}/install.sh" ]; then
    err "bundle 内未找到 install.sh"
    exit 1
  fi

  log "执行 SafetyHub 内置 install.sh"
  chmod +x "${inner_dir}/install.sh"
  bash "${inner_dir}/install.sh"

  log "部署完成。容器状态:"
  ( cd "${inner_dir}/NF-SafetyHub" && docker compose ps )
}

main() {
  require_root
  if [ "${SKIP_DOCKER_INSTALL:-false}" != "true" ]; then
    install_docker
  else
    log "SKIP_DOCKER_INSTALL=true, 跳过 docker 安装"
  fi

  if [ "${SKIP_APP_DEPLOY:-false}" != "true" ]; then
    deploy_app
  else
    log "SKIP_APP_DEPLOY=true, 跳过应用部署"
  fi
  log "全部完成"
}

main "$@"
