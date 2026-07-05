#!/usr/bin/env bash
# Start Anayaa.AI backend: deps, Ollama models, Milvus seed, FastAPI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
VENV_DIR="$BACKEND/anayaa"

log() { echo "[anayaa] $*"; }
warn() { echo "[anayaa] WARNING: $*" >&2; }

online_setup_required() {
  local reason="$1"
  echo "[anayaa] ERROR: ${reason}" >&2
  echo "[anayaa] OFFLINE_MODE=true uses only cached local dependencies and model assets." >&2
  echo "[anayaa] Connect to Wi-Fi and run the one-time setup:" >&2
  echo "[anayaa]   ./scripts/anayaa setup" >&2
  echo "[anayaa] Then start Anayaa again:" >&2
  echo "[anayaa]   ./scripts/anayaa serve" >&2
}

require_local_socket_support() {
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

  echo "[anayaa] ERROR: Milvus Lite cannot bind a local Unix socket in this shell." >&2
  echo "[anayaa] Run startup from a normal macOS Terminal or WSL/Linux shell, not a restricted/sandboxed shell:" >&2
  echo "[anayaa]   cd \"$ROOT\" && ./scripts/anayaa serve" >&2
  exit 1
}

migrate_env() {
  local env_file="$BACKEND/.env"
  [[ -f "$env_file" ]] || return 0

  if grep -q '^MILVUS_URI=' "$env_file" && ! grep -q '^ANAYAA_MILVUS_URI=' "$env_file"; then
    local val
    val="$(grep '^MILVUS_URI=' "$env_file" | head -1 | cut -d= -f2-)"
    echo "ANAYAA_MILVUS_URI=${val}" >> "$env_file"
    log "Copied MILVUS_URI -> ANAYAA_MILVUS_URI"
  fi

  if grep -q '^MILVUS_URI=' "$env_file"; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
      sed -i '' '/^MILVUS_URI=/d' "$env_file"
    else
      sed -i '/^MILVUS_URI=/d' "$env_file"
    fi
    log "Removed MILVUS_URI from .env (conflicts with pymilvus — use ANAYAA_MILVUS_URI)"
  fi

  if ! grep -q '^OFFLINE_MODE=' "$env_file"; then
    printf '\nOFFLINE_MODE=true\n' >> "$env_file"
    log "Added OFFLINE_MODE=true to backend/.env"
  fi

  if grep -q '^OLLAMA_BASE_URL=http://localhost:11434$' "$env_file"; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
      sed -i '' 's|^OLLAMA_BASE_URL=http://localhost:11434$|OLLAMA_BASE_URL=http://127.0.0.1:11434|' "$env_file"
    else
      sed -i 's|^OLLAMA_BASE_URL=http://localhost:11434$|OLLAMA_BASE_URL=http://127.0.0.1:11434|' "$env_file"
    fi
    log "Updated OLLAMA_BASE_URL to 127.0.0.1 for offline local use"
  fi

  if grep -q '^REDIS_URL=redis://localhost:6379/0$' "$env_file"; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
      sed -i '' 's|^REDIS_URL=redis://localhost:6379/0$|REDIS_URL=redis://127.0.0.1:6379/0|' "$env_file"
    else
      sed -i 's|^REDIS_URL=redis://localhost:6379/0$|REDIS_URL=redis://127.0.0.1:6379/0|' "$env_file"
    fi
    log "Updated REDIS_URL to 127.0.0.1 for offline local use"
  fi

  if grep -q '^POSTGRES_HOST=localhost$' "$env_file"; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
      sed -i '' 's|^POSTGRES_HOST=localhost$|POSTGRES_HOST=127.0.0.1|' "$env_file"
    else
      sed -i 's|^POSTGRES_HOST=localhost$|POSTGRES_HOST=127.0.0.1|' "$env_file"
    fi
    log "Updated POSTGRES_HOST to 127.0.0.1 for offline local use"
  fi
}

ensure_jwt_secret() {
  local env_file="$BACKEND/.env"
  local current=""
  local generated

  if grep -q '^JWT_SECRET=' "$env_file"; then
    current="$(grep '^JWT_SECRET=' "$env_file" | head -1 | cut -d= -f2-)"
  fi

  if [[ "$current" != "" \
    && "$current" != "change-me" \
    && "$current" != "change-me-generate-with-start-backend" \
    && "$current" != anayaa-edge-secret-key-* \
    && "${#current}" -ge 32 ]]; then
    return 0
  fi

  generated="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"

  if grep -q '^JWT_SECRET=' "$env_file"; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
      sed -i '' "s|^JWT_SECRET=.*|JWT_SECRET=${generated}|" "$env_file"
    else
      sed -i "s|^JWT_SECRET=.*|JWT_SECRET=${generated}|" "$env_file"
    fi
  else
    printf '\nJWT_SECRET=%s\n' "$generated" >> "$env_file"
  fi
  log "Generated a unique backend JWT_SECRET in backend/.env"
}

ensure_venv() {
  cd "$BACKEND"
  if [[ "${OFFLINE_MODE:-true}" == "true" ]]; then
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
      online_setup_required "backend/anayaa is missing. This usually happens after ./scripts/free-resources.sh --all --yes."
      exit 1
    fi

    if ! "$VENV_DIR/bin/python" - <<'PY'
import importlib.util
import sys

required = [
    "fastapi",
    "uvicorn",
    "redis",
    "mcp",
    "pymilvus",
    "sentence_transformers",
    "onnxruntime",
]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print(", ".join(missing), file=sys.stderr)
    sys.exit(1)
PY
    then
      online_setup_required "backend Python dependencies are not installed completely in backend/anayaa."
      exit 1
    fi

    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    log "Using cached Python dependencies (OFFLINE_MODE=true)."
    return 0
  fi

  if [[ ! -d "$VENV_DIR" ]]; then
    log "Creating Python virtual environment at backend/anayaa..."
    python3 -m venv "$VENV_DIR"
  fi
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
  log "Installing Python dependencies..."
  pip install -r requirements.txt -q
}

load_env() {
  cd "$BACKEND"
  local requested_offline_mode="${OFFLINE_MODE:-}"
  if [[ ! -f .env ]]; then
    cp .env.example .env
    log "Created backend/.env from .env.example"
  fi
  migrate_env
  ensure_jwt_secret
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  if [[ -n "$requested_offline_mode" ]]; then
    export OFFLINE_MODE="$requested_offline_mode"
  fi
  unset MILVUS_URI
}

ensure_ollama() {
  local base_url="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
  local models=(gemma2:2b qwen3:4b llama3.2:3b)

  if ! command -v ollama >/dev/null 2>&1; then
    warn "Ollama is not installed. Install from https://ollama.com then re-run this script."
    return 1
  fi

  if ! curl -sf "${base_url}/api/tags" >/dev/null 2>&1; then
    log "Ollama not responding — starting ollama serve in background..."
    nohup ollama serve >> "$ROOT/.ollama-serve.log" 2>&1 &
    for _ in $(seq 1 20); do
      if curl -sf "${base_url}/api/tags" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  fi

  if ! curl -sf "${base_url}/api/tags" >/dev/null 2>&1; then
    warn "Ollama still not reachable at ${base_url}. Start it manually: ollama serve"
    return 1
  fi

  for model in "${models[@]}"; do
    if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$model"; then
      log "Ollama model ready: $model"
    else
      log "Pulling Ollama model: $model (first run may take several minutes)..."
      ollama pull "$model"
    fi
  done
}

ensure_postgres() {
  local host="${POSTGRES_HOST:-127.0.0.1}"
  local port="${POSTGRES_PORT:-5432}"
  if pg_isready -h "$host" -p "$port" >/dev/null 2>&1; then
    log "PostgreSQL is running at ${host}:${port}"
    return 0
  fi
  echo "[anayaa] ERROR: PostgreSQL is required but not running at ${host}:${port}." >&2
  echo "[anayaa] Run: ./scripts/anayaa setup" >&2
  exit 1
}

ensure_redis() {
  local url="${REDIS_URL:-redis://127.0.0.1:6379/0}"
  if python - "$url" <<'PY'
import sys
from urllib.parse import urlparse
import redis

url = sys.argv[1]
parsed = urlparse(url)
client = redis.Redis(host=parsed.hostname or "127.0.0.1", port=parsed.port or 6379, db=int((parsed.path or "/0").lstrip("/") or 0))
client.ping()
PY
  then
    log "Redis is running at ${url}"
    return 0
  fi
  echo "[anayaa] ERROR: Redis is required but unavailable at ${url}." >&2
  echo "[anayaa] Start Redis, then re-run this script." >&2
  exit 1
}

ensure_milvus() {
  cd "$BACKEND"
  unset MILVUS_URI

  log "Checking Milvus Lite / vector seed..."
  set +e
  python - <<'PY'
import sys
from app.config import get_settings
from app.memory.milvus_store import MilvusStore
from app.retrieval.corpus import load_scriptures_json

settings = get_settings()
if not settings.milvus_enabled:
    print("[anayaa] ERROR: Milvus is required. Set MILVUS_ENABLED=true.", file=sys.stderr)
    sys.exit(1)

load_scriptures_json()
store = MilvusStore()
try:
    store.connect()
except Exception as exc:
    print("[anayaa] ERROR: Milvus connect failed.", file=sys.stderr)
    print(f"[anayaa]   {exc}", file=sys.stderr)
    print(f"[anayaa]   ANAYAA_MILVUS_URI={settings.milvus_uri}", file=sys.stderr)
    print("[anayaa]   Ensure milvus-lite is installed and MILVUS_URI is NOT set in .env.", file=sys.stderr)
    sys.exit(1)

count = store.entity_count()
store.close()
if count > 0:
    print(f"[anayaa] Milvus ready ({count} vectors indexed).")
    sys.exit(0)

print("[anayaa] Milvus collection empty — running seed script...")
sys.exit(2)
PY
  local status=$?
  set -e
  if [[ $status -eq 2 ]]; then
    seed_milvus
  elif [[ $status -ne 0 ]]; then
    exit "$status"
  fi
}

seed_milvus() {
  local seed_log
  seed_log="$(mktemp "${TMPDIR:-/tmp}/anayaa-seed.XXXXXX")"

  log "Seeding Milvus/PostgreSQL scripture data..."
  if [[ "${OFFLINE_MODE:-true}" == "true" ]]; then
    log "OFFLINE_MODE=true; seeding requires the embedding model to already be cached."
  fi

  set +e
  python scripts/seed_milvus.py 2>&1 | tee "$seed_log"
  local seed_status=${PIPESTATUS[0]}
  set -e

  if [[ $seed_status -eq 0 ]]; then
    rm -f "$seed_log"
    return 0
  fi

  if grep -qi "local cache\\|local_files_only\\|Embedding model is not available" "$seed_log"; then
    echo "[anayaa] ERROR: Milvus is empty, but the embedding model is not cached locally." >&2
    echo "[anayaa] Connect to Wi-Fi once and run: ./scripts/anayaa setup" >&2
    echo "[anayaa] That command installs dependencies, caches embedding assets, pulls Ollama models, and seeds retrieval." >&2
  else
    echo "[anayaa] ERROR: Milvus/PostgreSQL scripture seed failed." >&2
    echo "[anayaa] If this is a first-time setup or you recently ran cleanup with --storage/--all, run: ./scripts/anayaa setup" >&2
  fi

  rm -f "$seed_log"
  exit "$seed_status"
}

main() {
  log "Anayaa.AI backend startup"
  load_env
  ensure_venv
  ensure_ollama || true
  ensure_postgres
  ensure_redis
  require_local_socket_support
  ensure_milvus
  cd "$BACKEND"
  unset MILVUS_URI
  local port="${ANAYAA_PORT:-8000}"
  local host="${ANAYAA_HOST:-127.0.0.1}"
  local reload_args=()
  if [[ "${ANAYAA_RELOAD:-false}" == "true" ]]; then
    reload_args=(--reload)
  fi
  log "Starting Anayaa at http://${host}:${port}"
  if [[ "${#reload_args[@]}" -gt 0 ]]; then
    exec uvicorn app.main:app --host "$host" --port "$port" "${reload_args[@]}"
  fi
  exec uvicorn app.main:app --host "$host" --port "$port"
}

main "$@"
