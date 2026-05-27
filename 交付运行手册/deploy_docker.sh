#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

if [ ! -f ".env" ]; then
  cp "${DEPLOY_DIR}/.env.production.example" .env
  echo "Created .env from production example. Review it before real production use."
fi

docker compose up --build -d
docker compose ps
