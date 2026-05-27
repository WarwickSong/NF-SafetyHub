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

.venv/bin/python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
