#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

if [ ! -x ".venv/bin/python" ]; then
  "${DEPLOY_DIR}/setup_venv.sh"
fi

if [ ! -f ".env" ]; then
  cp "${DEPLOY_DIR}/.env.production.example" .env
fi

exec .venv/bin/python -m uvicorn main:app \
  --host "${UVICORN_HOST:-0.0.0.0}" \
  --port "${UVICORN_PORT:-4000}" \
  --workers "${UVICORN_WORKERS:-4}"
