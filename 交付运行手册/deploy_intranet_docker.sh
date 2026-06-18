#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

if [ ! -f ".env" ]; then
  echo ".env is required" >&2
  exit 1
fi

set -a
source .env
set +a

DATA_ROOT="${SAFETYHUB_DATA_ROOT:-/data/safetyhub}"
APP_DATA_DIR="${SAFETYHUB_DATA_DIR:-${DATA_ROOT}/app}"
POSTGRES_DATA_DIR="${SAFETYHUB_POSTGRES_DATA_DIR:-${DATA_ROOT}/postgres}"

mkdir -p "${APP_DATA_DIR}" "${POSTGRES_DATA_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

if [ "${SAFETYHUB_SKIP_BUILD:-false}" = "true" ]; then
  docker compose up -d postgres
else
  docker compose up --build -d postgres
fi

echo "rebuilding runtime tables while preserving api_keys..."
docker compose run --rm safetyhub python scripts/rebuild_runtime_tables_preserve_apikeys.py

if [ "${SAFETYHUB_SKIP_BUILD:-false}" = "true" ]; then
  docker compose up --no-build -d safetyhub nginx
else
  docker compose up --build -d safetyhub nginx
fi

docker compose ps

echo "waiting for safetyhub to become healthy..."
for i in $(seq 1 30); do
  status=$(docker inspect --format='{{.State.Health.Status}}' safetyhub-app 2>/dev/null || echo "unknown")
  if [ "$status" = "healthy" ]; then
    echo "safetyhub is healthy"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "WARNING: safetyhub did not become healthy within 60s (current status: $status)"
    echo "Check logs: docker compose logs safetyhub"
  fi
  sleep 2
done

curl -fsS "http://127.0.0.1:${SAFETYHUB_HTTP_PORT:-80}/health/ready" || true
echo
echo "SafetyHub backend: http://127.0.0.1:${SAFETYHUB_HTTP_PORT:-80}/admin/"
echo "SafetyHub public:  https://${SAFETYHUB_DOMAIN:-llm-safetyhub.nanfu.com}/admin/"
