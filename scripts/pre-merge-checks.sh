#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[pre-merge] Backend compile check"
cd "$ROOT_DIR"
python3 -m compileall backend/app backend/tests

echo "[pre-merge] Backend unit tests"
cd "$ROOT_DIR/backend"
if [[ -x "anayaa/bin/python" ]]; then
  anayaa/bin/python -m pytest tests
else
  python3 -m pytest tests
fi

echo "[pre-merge] Frontend build"
cd "$ROOT_DIR/frontend"
npm run build

echo "[pre-merge] All checks passed"
