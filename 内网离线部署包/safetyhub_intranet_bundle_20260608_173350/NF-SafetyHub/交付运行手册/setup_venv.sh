#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "${PROJECT_ROOT}"

if [ ! -x ".venv/bin/python" ]; then
  "${PYTHON_BIN}" -m venv .venv
fi

.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python --version
.venv/bin/python -m pip --version
