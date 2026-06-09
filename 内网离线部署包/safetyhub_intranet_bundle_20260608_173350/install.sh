#!/usr/bin/env bash
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${BUNDLE_DIR}/NF-SafetyHub"
IMAGE_TAR="${BUNDLE_DIR}/safetyhub-images.tar"
APIKEYS_SQL="$(find "${BUNDLE_DIR}/data" -maxdepth 1 -type f -name 'safetyhub_apikeys_*.sql' | sort | tail -n 1)"

cd "${APP_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

if [ ! -f "${IMAGE_TAR}" ]; then
  echo "image tar not found: ${IMAGE_TAR}" >&2
  exit 1
fi

docker load -i "${IMAGE_TAR}"

if [ ! -f ".env" ]; then
  echo "embedded env not found: ${APP_DIR}/.env" >&2
  exit 1
fi

if [ -z "${APIKEYS_SQL}" ] || [ ! -f "${APIKEYS_SQL}" ]; then
  echo "api keys sql file not found under ${BUNDLE_DIR}/data" >&2
  exit 1
fi

bash 交付运行手册/deploy_intranet_docker.sh "${APIKEYS_SQL}"
