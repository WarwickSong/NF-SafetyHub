#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"
APIKEYS_SQL="${1:-}"

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
  docker compose up --no-build -d safetyhub nginx
else
  docker compose up --build -d postgres
  docker compose up --build -d safetyhub nginx
fi

wait_for_table() {
  table_name="$1"
  for _ in $(seq 1 60); do
    if docker compose exec -T postgres psql -qAt -U "${POSTGRES_USER:-safetyhub}" -d "${POSTGRES_DB:-safetyhub}" \
      -c "SELECT to_regclass('public.${table_name}') IS NOT NULL;" | grep -qx 't'; then
      return 0
    fi
    sleep 2
  done
  echo "database table not ready: ${table_name}" >&2
  return 1
}

if [ -n "${APIKEYS_SQL}" ]; then
  if [ ! -f "${APIKEYS_SQL}" ]; then
    echo "api keys sql file not found: ${APIKEYS_SQL}" >&2
    exit 1
  fi
  echo "initializing database schema before importing api keys..."
  docker compose exec -T safetyhub python scripts/init_db.py
  wait_for_table api_keys

  {
    cat <<'SQL'
BEGIN;
DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'admin_operations',
    'approval_requests',
    'approval_chains',
    'audit_logs',
    'image_assets',
    'message_archives',
    'security_policies',
    'api_keys'
  ] LOOP
    IF to_regclass('public.' || table_name) IS NOT NULL THEN
      EXECUTE format('TRUNCATE TABLE %I RESTART IDENTITY CASCADE', table_name);
    END IF;
  END LOOP;
END $$;
SQL
    cat "${APIKEYS_SQL}"
    echo "COMMIT;"
  } | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-safetyhub}" -d "${POSTGRES_DB:-safetyhub}"
fi

docker compose ps
curl -fsS "http://127.0.0.1:${SAFETYHUB_HTTP_PORT:-80}/health/ready" || true
echo
echo "SafetyHub backend: http://127.0.0.1:${SAFETYHUB_HTTP_PORT:-80}/admin/"
echo "SafetyHub public:  https://${SAFETYHUB_DOMAIN:-llm-safetyhub.nanfu.com}/admin/"
