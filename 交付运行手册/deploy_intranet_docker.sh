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
REPORTS_HOST_DIR="${APP_DATA_DIR}/reports"

mkdir -p "${APP_DATA_DIR}" "${POSTGRES_DATA_DIR}" "${REPORTS_HOST_DIR}"

if ! chown -R 1000:1000 "${REPORTS_HOST_DIR}" 2>/dev/null; then
  chmod -R a+rwX "${REPORTS_HOST_DIR}"
fi

if [ ! -w "${REPORTS_HOST_DIR}" ]; then
  echo "reports directory is not writable: ${REPORTS_HOST_DIR}" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

if [ "${SAFETYHUB_SKIP_BUILD:-false}" = "true" ]; then
  docker compose up -d postgres
else
  docker compose up --build -d postgres
fi

echo "waiting for postgres to be ready..."
for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "ERROR: postgres did not become ready, aborting deployment" >&2
    exit 1
  fi
  sleep 2
done

echo "backing up api_keys before rebuilding tables..."
APIKEY_BACKUP_DIR="${APP_DATA_DIR}/apikey_backups"
mkdir -p "${APIKEY_BACKUP_DIR}"
APIKEY_BACKUP_FILE="${APIKEY_BACKUP_DIR}/api_keys_$(date +%Y%m%d_%H%M%S).sql"

set +e
APIKEY_TABLE_EXISTS="$(docker compose exec -T postgres env PGPASSWORD="${POSTGRES_PASSWORD}" \
  psql -h 127.0.0.1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
  "SELECT to_regclass('public.api_keys') IS NOT NULL")"
APIKEY_CHECK_RC=$?
set -e
if [ "${APIKEY_CHECK_RC}" -ne 0 ]; then
  echo "ERROR: cannot check api_keys existence, aborting deployment" >&2
  exit 1
fi
APIKEY_TABLE_EXISTS="$(printf '%s' "${APIKEY_TABLE_EXISTS}" | tr -d '[:space:]')"

if [ "${APIKEY_TABLE_EXISTS}" = "t" ]; then
  if ! docker compose exec -T postgres env PGPASSWORD="${POSTGRES_PASSWORD}" \
      pg_dump -h 127.0.0.1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
      --data-only --column-inserts --table=public.api_keys > "${APIKEY_BACKUP_FILE}"; then
    echo "ERROR: api_keys backup failed, aborting deployment" >&2
    rm -f "${APIKEY_BACKUP_FILE}"
    exit 1
  fi
  if [ ! -s "${APIKEY_BACKUP_FILE}" ]; then
    echo "ERROR: api_keys backup file is empty, aborting deployment" >&2
    rm -f "${APIKEY_BACKUP_FILE}"
    exit 1
  fi
  sha256sum "${APIKEY_BACKUP_FILE}" > "${APIKEY_BACKUP_FILE}.sha256"
  echo "api_keys backup done: ${APIKEY_BACKUP_FILE}"
else
  echo "api_keys table not found (fresh database), skip backup"
fi

echo "rebuilding runtime tables while preserving api_keys..."
docker compose run --rm -e PYTHONPATH=/app safetyhub python scripts/rebuild_runtime_tables_preserve_apikeys.py

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
echo "SafetyHub reports: ${REPORTS_HOST_DIR} -> /app/data/reports"
