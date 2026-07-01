#!/usr/bin/env bash
# One-time online setup: install deps, pull local LLMs, cache HF assets, seed retrieval.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV_DIR="$BACKEND/anayaa"
OLLAMA_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"

log() { echo "[anayaa-online-setup] $*"; }
warn() { echo "[anayaa-online-setup] WARNING: $*" >&2; }

require_online() {
  log "Checking internet access for dependency and model setup..."
  if command -v curl >/dev/null 2>&1 \
    && curl -fsI --connect-timeout 5 https://pypi.org/simple/fastapi/ >/dev/null 2>&1; then
    return 0
  fi

  echo "[anayaa-online-setup] ERROR: Online setup requires internet access." >&2
  echo "[anayaa-online-setup] Connect to Wi-Fi and re-run: ./scripts/setup-online.sh" >&2
  echo "[anayaa-online-setup] This step installs Python/npm dependencies, caches embedding assets, pulls Ollama models, and seeds retrieval." >&2
  exit 1
}

require_local_socket_support() {
  log "Checking local socket support for Milvus Lite..."
  if python3 - <<'PY'
import os
import socket
import sys
from pathlib import Path

sock_path = Path("/tmp/anayaa-ml.sock")
try:
    if sock_path.exists():
        sock_path.unlink()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(sock_path))
    sock.close()
    sock_path.unlink()
except OSError as exc:
    print(exc, file=sys.stderr)
    sys.exit(1)
PY
  then
    return 0
  fi

  echo "[anayaa-online-setup] ERROR: Milvus Lite cannot bind a local Unix socket in this shell." >&2
  echo "[anayaa-online-setup] Milvus Lite needs local socket permissions to seed backend/data/milvus.db." >&2
  echo "[anayaa-online-setup] Run this command from a normal macOS Terminal window, not a restricted/sandboxed shell:" >&2
  echo "[anayaa-online-setup]   cd \"$ROOT\" && ./scripts/setup-online.sh" >&2
  exit 1
}

ensure_env() {
  if [[ ! -f "$BACKEND/.env" ]]; then
    cp "$BACKEND/.env.example" "$BACKEND/.env"
    log "Created backend/.env from .env.example"
  fi
}

replace_env_line() {
  local key="$1"
  local value="$2"
  local env_file="$BACKEND/.env"

  if grep -q "^${key}=" "$env_file"; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
      sed -i '' "s|^${key}=.*|${key}=${value}|" "$env_file"
    else
      sed -i "s|^${key}=.*|${key}=${value}|" "$env_file"
    fi
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$env_file"
  fi
}

normalize_env() {
  replace_env_line "OFFLINE_MODE" "true"

  if grep -q '^MILVUS_URI=' "$BACKEND/.env" && ! grep -q '^ANAYAA_MILVUS_URI=' "$BACKEND/.env"; then
    local val
    val="$(grep '^MILVUS_URI=' "$BACKEND/.env" | head -1 | cut -d= -f2-)"
    replace_env_line "ANAYAA_MILVUS_URI" "$val"
    log "Copied MILVUS_URI -> ANAYAA_MILVUS_URI"
  fi

  if grep -q '^MILVUS_URI=' "$BACKEND/.env"; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
      sed -i '' '/^MILVUS_URI=/d' "$BACKEND/.env"
    else
      sed -i '/^MILVUS_URI=/d' "$BACKEND/.env"
    fi
    log "Removed MILVUS_URI from backend/.env; use ANAYAA_MILVUS_URI for Anayaa Milvus Lite"
  fi

  if grep -q '^OLLAMA_BASE_URL=http://localhost:11434$' "$BACKEND/.env"; then
    replace_env_line "OLLAMA_BASE_URL" "http://127.0.0.1:11434"
  fi
  if grep -q '^REDIS_URL=redis://localhost:6379/0$' "$BACKEND/.env"; then
    replace_env_line "REDIS_URL" "redis://127.0.0.1:6379/0"
  fi
  if grep -q '^POSTGRES_HOST=localhost$' "$BACKEND/.env"; then
    replace_env_line "POSTGRES_HOST" "127.0.0.1"
  fi
}

ensure_jwt_secret() {
  local current=""
  local generated

  if grep -q '^JWT_SECRET=' "$BACKEND/.env"; then
    current="$(grep '^JWT_SECRET=' "$BACKEND/.env" | head -1 | cut -d= -f2-)"
  fi

  if [[ "$current" != "" \
    && "$current" != "change-me" \
    && "$current" != "change-me-generate-with-start-backend" \
    && "$current" != anayaa-edge-secret-key-* \
    && "${#current}" -ge 32 ]]; then
    return 0
  fi

  generated="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  replace_env_line "JWT_SECRET" "$generated"
  log "Generated a unique backend JWT_SECRET in backend/.env"
}

ensure_backend_deps() {
  cd "$BACKEND"
  if [[ ! -d "$VENV_DIR" ]]; then
    log "Creating Python virtual environment at backend/anayaa..."
    python3 -m venv "$VENV_DIR"
  fi
  log "Installing backend Python dependencies..."
  "$VENV_DIR/bin/python" -m pip install -r requirements.txt
}

ensure_frontend_deps() {
  cd "$FRONTEND"
  log "Installing frontend npm dependencies..."
  npm install
}

build_frontend() {
  cd "$FRONTEND"
  log "Building frontend for local Anayaa serve..."
  npm run build
}

ensure_ollama_models() {
  local models=(gemma2:2b qwen3:4b llama3.2:3b)

  if ! command -v ollama >/dev/null 2>&1; then
    warn "Ollama is not installed. Install Ollama, then run: ollama pull gemma2:2b && ollama pull qwen3:4b && ollama pull llama3.2:3b"
    return 0
  fi

  if ! curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
    log "Ollama not responding; starting ollama serve in background..."
    nohup ollama serve >> "$ROOT/.ollama-serve.log" 2>&1 &
    for _ in $(seq 1 20); do
      if curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  fi

  if ! curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
    warn "Ollama is still unavailable at ${OLLAMA_URL}; skipping model pulls."
    return 0
  fi

  for model in "${models[@]}"; do
    if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$model"; then
      log "Ollama model already present: $model"
    else
      log "Pulling Ollama model: $model"
      ollama pull "$model"
    fi
  done
}

cache_embedding_model() {
  cd "$BACKEND"
  unset MILVUS_URI
  log "Caching embedding model for later OFFLINE_MODE=true runtime..."
  OFFLINE_MODE=false "$VENV_DIR/bin/python" scripts/cache_runtime_assets.py
}

seed_retrieval() {
  cd "$BACKEND"
  unset MILVUS_URI
  log "Seeding PostgreSQL and Milvus Lite scripture data..."
  OFFLINE_MODE=false "$VENV_DIR/bin/python" scripts/seed_milvus.py
}

main() {
  log "Starting online setup. Keep Wi-Fi on for this step."
  require_online
  require_local_socket_support
  ensure_env
  normalize_env
  ensure_jwt_secret
  ensure_backend_deps
  ensure_frontend_deps
  build_frontend
  ensure_ollama_models
  cache_embedding_model
  seed_retrieval
  log "Online setup complete. You can now run Anayaa with OFFLINE_MODE=true:"
  log "  ./scripts/anayaa serve"
}

main "$@"
