#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"
OUTPUT_DIR="${1:-${PROJECT_ROOT}/data/export}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
EXPORT_FILE="${OUTPUT_DIR}/safetyhub_apikeys_${TIMESTAMP}.sql"

cd "${PROJECT_ROOT}"

if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi

DB_URL_VALUE="${DB_URL:-${POSTGRES_DB_URL:-}}"
if [ -z "${DB_URL_VALUE}" ]; then
  echo "DB_URL or POSTGRES_DB_URL is required" >&2
  exit 1
fi

if [[ "${DB_URL_VALUE}" != postgresql+asyncpg://* ]]; then
  echo "only postgresql+asyncpg:// source database is supported" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"
PG_URL="${DB_URL_VALUE/postgresql+asyncpg:\/\//postgresql://}"

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "pg_dump is required on source server" >&2
  exit 1
fi

pg_dump "${PG_URL}" \
  --data-only \
  --column-inserts \
  --table=api_keys \
  --file="${EXPORT_FILE}"

sha256sum "${EXPORT_FILE}" > "${EXPORT_FILE}.sha256"
echo "exported ${EXPORT_FILE}"
echo "checksum ${EXPORT_FILE}.sha256"
