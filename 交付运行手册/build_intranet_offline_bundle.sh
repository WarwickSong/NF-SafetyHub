#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"
OUTPUT_ROOT="${1:-${PROJECT_ROOT}/内网离线部署包}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BUNDLE_NAME="safetyhub_intranet_bundle_${TIMESTAMP}"
BUNDLE_DIR="${OUTPUT_ROOT}/${BUNDLE_NAME}"
APP_DIR="${BUNDLE_DIR}/NF-SafetyHub"
IMAGE_TAR="${BUNDLE_DIR}/safetyhub-images.tar"
SAFETYHUB_IMAGE_NAME="${SAFETYHUB_IMAGE:-nf-safetyhub-safetyhub:latest}"

cd "${PROJECT_ROOT}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

mkdir -p "${APP_DIR}" "${BUNDLE_DIR}/data"

bash "${DEPLOY_DIR}/export_apikeys_for_intranet.sh" "${BUNDLE_DIR}/data"

docker compose build safetyhub
if [ "${SAFETYHUB_SKIP_PULL:-false}" != "true" ]; then
  docker pull postgres:16-alpine
  docker pull nginx:1.27-alpine
fi
docker save "${SAFETYHUB_IMAGE_NAME}" postgres:16-alpine nginx:1.27-alpine -o "${IMAGE_TAR}"

tar \
  --exclude='./.git' \
  --exclude='./.venv' \
  --exclude='./.env' \
  --exclude='./data' \
  --exclude='./__pycache__' \
  --exclude='./.pytest_cache' \
  --exclude='./内网离线部署包' \
  -cf - . | tar -C "${APP_DIR}" --strip-components=1 -xf -

BUNDLE_ENV_TEMPLATE="${OUTPUT_ROOT}/intranet.env"
if [ ! -f "${BUNDLE_ENV_TEMPLATE}" ]; then
  echo "${BUNDLE_ENV_TEMPLATE} is required for intranet bundle" >&2
  exit 1
fi
cp "${BUNDLE_ENV_TEMPLATE}" "${APP_DIR}/.env"

cat > "${BUNDLE_DIR}/install.sh" <<'SH'
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
SH
chmod +x "${BUNDLE_DIR}/install.sh" "${APP_DIR}/交付运行手册/deploy_intranet_docker.sh"

tar -C "${OUTPUT_ROOT}" -czf "${OUTPUT_ROOT}/${BUNDLE_NAME}.tar.gz" "${BUNDLE_NAME}"
sha256sum "${OUTPUT_ROOT}/${BUNDLE_NAME}.tar.gz" > "${OUTPUT_ROOT}/${BUNDLE_NAME}.tar.gz.sha256"

echo "bundle dir: ${BUNDLE_DIR}"
echo "bundle tar: ${OUTPUT_ROOT}/${BUNDLE_NAME}.tar.gz"
echo "checksum: ${OUTPUT_ROOT}/${BUNDLE_NAME}.tar.gz.sha256"
