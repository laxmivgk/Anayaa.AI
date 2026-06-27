#!/usr/bin/env bash
# One-time online setup: install deps, pull local LLMs, cache HF assets, seed retrieval.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
OLLAMA_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"

log() { echo "[anayaa-online-setup] $*"; }
warn() { echo "[anayaa-online-setup] WARNING: $*" >&2; }

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
  if [[ ! -d .venv ]]; then
    log "Creating Python virtual environment..."
    python3 -m venv .venv
  fi
  log "Installing backend Python dependencies..."
  .venv/bin/python -m pip install -r requirements.txt
}

ensure_frontend_deps() {
  cd "$FRONTEND"
  log "Installing frontend npm dependencies..."
  npm install
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
  log "Caching embedding model for later OFFLINE_MODE=true runtime..."
  OFFLINE_MODE=false .venv/bin/python scripts/cache_runtime_assets.py
}

seed_retrieval() {
  cd "$BACKEND"
  log "Seeding PostgreSQL and Milvus Lite scripture data..."
  OFFLINE_MODE=false .venv/bin/python scripts/seed_milvus.py
}

main() {
  log "Starting online setup. Keep Wi-Fi on for this step."
  ensure_env
  normalize_env
  ensure_jwt_secret
  ensure_backend_deps
  ensure_frontend_deps
  ensure_ollama_models
  cache_embedding_model
  seed_retrieval
  log "Online setup complete. You can now run Anayaa with OFFLINE_MODE=true:"
  log "  ./scripts/start-backend.sh"
  log "  ./scripts/start-frontend.sh"
}

main "$@"
