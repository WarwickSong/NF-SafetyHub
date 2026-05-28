#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

if [ ! -x ".venv/bin/python" ]; then
  "${DEPLOY_DIR}/setup_venv.sh"
fi

.venv/bin/python -m pytest tests/test_fake_response.py tests/test_header_policy.py tests/test_relay.py tests/test_upstream_router.py
