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
  echo "Created .env from production example. Review it before real production use."
fi

.venv/bin/python scripts/init_db.py
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
