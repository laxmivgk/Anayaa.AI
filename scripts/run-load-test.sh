#!/usr/bin/env bash
# Run a lightweight Anayaa API load test against a live backend.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
USERS="${USERS:-3}"
DURATION_SECONDS="${DURATION_SECONDS:-60}"
P95_MS="${P95_MS:-60000}"
PRE_SYNTHESIS="${PRE_SYNTHESIS:-false}"
QUERY="${QUERY:-How can I resolve a disagreement with a close friend honestly and compassionately?}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ -z "${ANAYAA_LOAD_TEST_PASSWORD:-}" ]]; then
  echo "[anayaa-load] ERROR: ANAYAA_LOAD_TEST_PASSWORD must be set for load tests." >&2
  echo "[anayaa-load] Create that user with: cd backend && python scripts/create_user.py --email \${ANAYAA_LOAD_TEST_EMAIL:-codex.test@example.com}" >&2
  exit 1
fi

if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
fi

pre_synthesis_arg=()
if [[ "$PRE_SYNTHESIS" == "true" ]]; then
  pre_synthesis_arg=(--pre-synthesis)
fi

echo "[anayaa-load] Target: ${BASE_URL}"
echo "[anayaa-load] Users: ${USERS}"
echo "[anayaa-load] Duration: ${DURATION_SECONDS}s"
echo "[anayaa-load] p95 threshold: ${P95_MS} ms"
echo "[anayaa-load] preSynthesisVerification: ${PRE_SYNTHESIS}"

"$PYTHON_BIN" "$ROOT_DIR/scripts/load_test.py" \
  --base-url "$BASE_URL" \
  --users "$USERS" \
  --duration-seconds "$DURATION_SECONDS" \
  --p95-ms "$P95_MS" \
  --query "$QUERY" \
  "${pre_synthesis_arg[@]}"
