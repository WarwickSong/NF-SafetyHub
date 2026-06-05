#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

if [ ! -x ".venv/bin/python" ]; then
  "${DEPLOY_DIR}/setup_venv.sh"
fi

if [ ! -f ".env" ]; then
  cp "${DEPLOY_DIR}/.env.local.example" .env
fi

export WATCHFILES_FORCE_POLLING="${WATCHFILES_FORCE_POLLING:-true}"

.venv/bin/python -m uvicorn main:app \
  --reload \
  --reload-dir admin \
  --reload-dir engine \
  --reload-dir governance \
  --reload-dir middleware \
  --reload-dir observability \
  --reload-dir proxy \
  --reload-dir storage \
  --reload-dir config.py \
  --reload-dir dependencies.py \
  --reload-dir main.py \
  --reload-exclude admin/static \
  --host 0.0.0.0 \
  --port 4000
