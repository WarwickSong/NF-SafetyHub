#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"
APIKEYS_SQL="${1:-}"

cd "${PROJECT_ROOT}"

if [ ! -f ".env" ]; then
  cp "${DEPLOY_DIR}/.env.production.example" .env
  echo "created .env from production example; edit .env and rerun this script" >&2
  exit 2
fi

set -a
source .env
set +a

DATA_ROOT="${SAFETYHUB_DATA_ROOT:-/data/safetyhub}"
APP_DATA_DIR="${SAFETYHUB_DATA_DIR:-${DATA_ROOT}/app}"
POSTGRES_DATA_DIR="${SAFETYHUB_POSTGRES_DATA_DIR:-${DATA_ROOT}/postgres}"

mkdir -p "${APP_DATA_DIR}" "${POSTGRES_DATA_DIR}"

if grep -q "replace-with-" .env; then
  echo "replace placeholder values in .env before deployment" >&2
  grep -n "replace-with-" .env >&2 || true
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

docker compose up --build -d postgres
docker compose up --build -d safetyhub nginx

if [ -n "${APIKEYS_SQL}" ]; then
  if [ ! -f "${APIKEYS_SQL}" ]; then
    echo "api keys sql file not found: ${APIKEYS_SQL}" >&2
    exit 1
  fi
  {
    cat <<'SQL'
BEGIN;
TRUNCATE TABLE
  admin_operations,
  approval_requests,
  approval_chains,
  audit_logs,
  image_assets,
  message_archives,
  security_policies
RESTART IDENTITY CASCADE;
TRUNCATE TABLE api_keys RESTART IDENTITY CASCADE;
SQL
    cat "${APIKEYS_SQL}"
    echo "COMMIT;"
  } | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-safetyhub}" -d "${POSTGRES_DB:-safetyhub}"
fi

docker compose ps
curl -fsS "http://127.0.0.1:${SAFETYHUB_HTTP_PORT:-8080}/health/ready" || true
echo
echo "SafetyHub admin: http://127.0.0.1:${SAFETYHUB_HTTP_PORT:-8080}/admin/"
