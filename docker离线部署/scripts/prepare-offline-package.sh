#!/usr/bin/env bash
# 在“有外网”的机器上执行，准备 docker + docker compose 离线安装资源，
# 并把 NF-SafetyHub 的离线镜像 bundle 一并打包成可整体拷贝到内网服务器的目录。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "${ROOT_DIR}/.." && pwd)"
DOCKER_DIR="${ROOT_DIR}/docker"
APP_BUNDLE_DIR="${ROOT_DIR}/app-bundle"
# 最终交付产物的默认输出目录：docker离线部署/部署文件/
# 调用方可通过 PKG_OUTPUT_DIR 覆盖（绝对/相对路径都允许，相对路径基于当前工作目录解析）。
PKG_OUTPUT_DIR_RAW="${PKG_OUTPUT_DIR:-${ROOT_DIR}/部署文件}"
mkdir -p "${PKG_OUTPUT_DIR_RAW}"
PKG_OUTPUT_DIR="$(cd "${PKG_OUTPUT_DIR_RAW}" && pwd)"

# 默认锁定到目标内网服务器使用的版本，必要时可以通过环境变量覆盖。
DOCKER_VERSION="${DOCKER_VERSION:-27.3.1}"
COMPOSE_VERSION="${COMPOSE_VERSION:-v2.29.7}"
ARCH="${ARCH:-x86_64}"                  # docker 静态包架构（x86_64 / aarch64）
COMPOSE_ARCH="${COMPOSE_ARCH:-x86_64}"  # compose 二进制架构

DOCKER_TGZ="docker-${DOCKER_VERSION}.tgz"
COMPOSE_BIN="docker-compose-linux-${COMPOSE_ARCH}"

# 多源回退：默认优先走国内镜像，避开 download.docker.com / github.com 被墙。
# 可用 DOCKER_URLS / COMPOSE_URLS 环境变量整体覆盖（空格分隔的多个 URL）。
DEFAULT_DOCKER_URLS=(
  "https://mirrors.aliyun.com/docker-ce/linux/static/stable/${ARCH}/${DOCKER_TGZ}"
  "https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/static/stable/${ARCH}/${DOCKER_TGZ}"
  "https://mirror.nju.edu.cn/docker-ce/linux/static/stable/${ARCH}/${DOCKER_TGZ}"
  "https://download.docker.com/linux/static/stable/${ARCH}/${DOCKER_TGZ}"
)
DEFAULT_COMPOSE_URLS=(
  "https://gh-proxy.com/https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/${COMPOSE_BIN}"
  "https://ghfast.top/https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/${COMPOSE_BIN}"
  "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/${COMPOSE_BIN}"
)

# shellcheck disable=SC2206
DOCKER_URLS=( ${DOCKER_URLS:-${DEFAULT_DOCKER_URLS[@]}} )
# shellcheck disable=SC2206
COMPOSE_URLS=( ${COMPOSE_URLS:-${DEFAULT_COMPOSE_URLS[@]}} )

# NF-SafetyHub 仓库根目录：默认就是 docker离线部署/ 的上级目录（即仓库根本身）。
# 调用方如果把 docker离线部署/ 单独拷出来，可显式传 NF_PROJECT_ROOT 指向真正的仓库根。
NF_PROJECT_ROOT="${NF_PROJECT_ROOT:-${PROJECT_ROOT}}"
NF_BUNDLE_OUTPUT_ROOT="${NF_PROJECT_ROOT}/内网离线部署包"

log() { printf '[prepare] %s\n' "$*"; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require_cmd curl
require_cmd tar
require_cmd sha256sum
require_cmd cmp

mkdir -p "${DOCKER_DIR}" "${APP_BUNDLE_DIR}"

verify_bundle_matches_source() {
  local bundle="$1"
  local bundle_root list_file
  list_file="$(mktemp)"
  tar -tzf "${bundle}" > "${list_file}"
  bundle_root="$(awk -F/ 'NF >= 2 && $2 == "NF-SafetyHub" {print $1; exit}' "${list_file}")"
  if [ -z "${bundle_root}" ]; then
    rm -f "${list_file}"
    echo "bundle 内未找到 NF-SafetyHub 目录: ${bundle}" >&2
    exit 1
  fi
  rm -f "${list_file}"

  local rel tmp_file
  for rel in docker-compose.yml nginx/nginx.conf 交付运行手册/deploy_intranet_docker.sh scripts/rebuild_runtime_tables_preserve_apikeys.py; do
    tmp_file="$(mktemp)"
    tar -xOzf "${bundle}" "${bundle_root}/NF-SafetyHub/${rel}" > "${tmp_file}"
    if ! cmp -s "${NF_PROJECT_ROOT}/${rel}" "${tmp_file}"; then
      rm -f "${tmp_file}"
      echo "最新 SafetyHub bundle 与当前源码不一致: ${rel}" >&2
      echo "请先重新执行: bash 交付运行手册/build_intranet_offline_bundle.sh" >&2
      exit 1
    fi
    rm -f "${tmp_file}"
  done
}

download_first_ok() {
  # 用法: download_first_ok <输出文件> <url1> [<url2> ...]
  local out="$1"; shift
  local url
  for url in "$@"; do
    log "尝试下载: ${url}"
    if curl -fL --retry 3 --connect-timeout 10 --max-time 600 -o "${out}.part" "${url}"; then
      mv "${out}.part" "${out}"
      log "下载成功: ${url}"
      return 0
    fi
    log "失败, 切换下一个源"
    rm -f "${out}.part"
  done
  return 1
}

# 1. 下载 docker 静态二进制
if [ ! -f "${DOCKER_DIR}/${DOCKER_TGZ}" ]; then
  log "下载 Docker ${DOCKER_VERSION} (${ARCH}) ..."
  if ! download_first_ok "${DOCKER_DIR}/${DOCKER_TGZ}" "${DOCKER_URLS[@]}"; then
    err_msg="所有 docker 下载源均失败。
请手动下载 ${DOCKER_TGZ} 到 ${DOCKER_DIR}/ 后重新运行本脚本。
可用源参考:
  - https://mirrors.aliyun.com/docker-ce/linux/static/stable/${ARCH}/
  - https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/static/stable/${ARCH}/
  - https://mirror.nju.edu.cn/docker-ce/linux/static/stable/${ARCH}/"
    echo "${err_msg}" >&2
    exit 1
  fi
else
  log "已存在 ${DOCKER_TGZ}, 跳过下载"
fi

# 2. 下载 docker compose v2 单文件二进制
if [ ! -f "${DOCKER_DIR}/${COMPOSE_BIN}" ]; then
  log "下载 docker compose ${COMPOSE_VERSION} (${COMPOSE_ARCH}) ..."
  if ! download_first_ok "${DOCKER_DIR}/${COMPOSE_BIN}" "${COMPOSE_URLS[@]}"; then
    echo "所有 docker compose 下载源均失败, 请手动下载 ${COMPOSE_BIN} 到 ${DOCKER_DIR}/" >&2
    exit 1
  fi
  chmod +x "${DOCKER_DIR}/${COMPOSE_BIN}"
else
  log "已存在 ${COMPOSE_BIN}, 跳过下载"
fi

# 3. 写出版本清单, 便于在内网核对
cat > "${DOCKER_DIR}/VERSIONS.txt" <<EOF
docker_version=${DOCKER_VERSION}
docker_arch=${ARCH}
compose_version=${COMPOSE_VERSION}
compose_arch=${COMPOSE_ARCH}
prepared_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

# 4. 校验和
( cd "${DOCKER_DIR}" && sha256sum "${DOCKER_TGZ}" "${COMPOSE_BIN}" > SHA256SUMS )

# 5. 同步最新的 NF-SafetyHub 镜像 bundle
if [ -d "${NF_BUNDLE_OUTPUT_ROOT}" ]; then
  LATEST_BUNDLE="$(ls -1t "${NF_BUNDLE_OUTPUT_ROOT}"/safetyhub_intranet_bundle_*.tar.gz 2>/dev/null | head -n1 || true)"
  if [ -n "${LATEST_BUNDLE}" ]; then
    verify_bundle_matches_source "${LATEST_BUNDLE}"
    log "复制最新 SafetyHub 镜像 bundle: ${LATEST_BUNDLE}"
    cp -f "${LATEST_BUNDLE}" "${APP_BUNDLE_DIR}/"
    ( cd "${APP_BUNDLE_DIR}" && sha256sum "$(basename "${LATEST_BUNDLE}")" > "$(basename "${LATEST_BUNDLE}").sha256" )
  else
    log "WARNING: ${NF_BUNDLE_OUTPUT_ROOT} 下没有 safetyhub_intranet_bundle_*.tar.gz, 请先在源机器执行 build_intranet_offline_bundle.sh"
  fi
else
  log "WARNING: 未找到 ${NF_BUNDLE_OUTPUT_ROOT}, 跳过应用 bundle 同步"
fi

# 6. 整体打包
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
PKG_NAME="docker-offline-deploy_${TIMESTAMP}.tar.gz"
# 成品默认放到 docker离线部署/部署文件/，避免“边打包边写文件”导致 tar 警告。
# 该目录与 ROOT_DIR 在同一仓库下，但 tar 时通过 --exclude 排除掉，防止把刚生成的包再打进去。
PKG_OUT="${PKG_OUTPUT_DIR}/${PKG_NAME}"

log "打包整个离线部署目录 -> ${PKG_OUT}"
tar -C "$(dirname "${ROOT_DIR}")" \
    --exclude="$(basename "${ROOT_DIR}")/部署文件" \
    -czf "${PKG_OUT}" "$(basename "${ROOT_DIR}")"
# 仅写入文件名（不含路径），保证拷贝到任意目录都能 sha256sum -c
( cd "${PKG_OUTPUT_DIR}" && sha256sum "${PKG_NAME}" > "${PKG_NAME}.sha256" )

log "完成。请将以下两个文件拷贝到内网服务器:"
log "  ${PKG_OUT}"
log "  ${PKG_OUT}.sha256"
