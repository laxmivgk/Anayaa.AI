#!/usr/bin/env bash
# Clean local generated files for Anayaa.AI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: ./scripts/clean-local.sh [options]

Default cleanup:
  - Python __pycache__ and .pytest_cache folders
  - frontend/dist
  - Vite cache under frontend/node_modules/.vite

Options:
  --deps    Also remove backend/.venv and frontend/node_modules
  --data    Also remove backend/data/milvus.db and local Ollama startup log
  --yes     Do not prompt before --data cleanup
  --help    Show this help
EOF
}

REMOVE_DEPS=false
REMOVE_DATA=false
ASSUME_YES=false

for arg in "$@"; do
  case "$arg" in
    --deps) REMOVE_DEPS=true ;;
    --data) REMOVE_DATA=true ;;
    --yes) ASSUME_YES=true ;;
    --help) usage; exit 0 ;;
    *) echo "[anayaa] Unknown option: $arg" >&2; usage; exit 1 ;;
  esac
done

log() { echo "[anayaa] $*"; }

log "Cleaning generated caches and build output..."
find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type d -name .pytest_cache -prune -exec rm -rf {} +
rm -rf "$ROOT/frontend/dist"
rm -rf "$ROOT/frontend/node_modules/.vite"

if [[ "$REMOVE_DEPS" == true ]]; then
  log "Removing dependency folders..."
  rm -rf "$ROOT/backend/.venv"
  rm -rf "$ROOT/frontend/node_modules"
fi

if [[ "$REMOVE_DATA" == true ]]; then
  if [[ "$ASSUME_YES" != true ]]; then
    read -r -p "[anayaa] Remove local Milvus data and startup logs? Type 'yes' to continue: " answer
    if [[ "$answer" != "yes" ]]; then
      log "Skipped data cleanup."
      exit 0
    fi
  fi
  log "Removing local Milvus data and startup logs..."
  rm -f "$ROOT/backend/data/milvus.db"
  rm -f "$ROOT/.ollama-serve.log"
fi

log "Clean complete."
