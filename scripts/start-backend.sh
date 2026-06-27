#!/usr/bin/env bash
# Start Anayaa.AI backend: deps, Ollama models, Milvus seed, FastAPI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"

log() { echo "[anayaa] $*"; }
warn() { echo "[anayaa] WARNING: $*" >&2; }

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
<<<<<<< HEAD

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
=======
>>>>>>> origin/main
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
  if [[ ! -d .venv ]]; then
    log "Creating Python virtual environment..."
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  log "Installing Python dependencies..."
  pip install -r requirements.txt -q
}

load_env() {
  cd "$BACKEND"
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
  unset MILVUS_URI
}

ensure_ollama() {
<<<<<<< HEAD
  local base_url="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
  local models=(gemma2:2b qwen3:4b llama3.2:3b)
=======
  local base_url="${OLLAMA_BASE_URL:-http://localhost:11434}"
  local models=(gemma2:2b llama3.1:8b llama3.2:3b)
>>>>>>> origin/main

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
<<<<<<< HEAD
  local host="${POSTGRES_HOST:-127.0.0.1}"
=======
  local host="${POSTGRES_HOST:-localhost}"
>>>>>>> origin/main
  local port="${POSTGRES_PORT:-5432}"
  if pg_isready -h "$host" -p "$port" >/dev/null 2>&1; then
    log "PostgreSQL is running at ${host}:${port}"
    return 0
  fi
  echo "[anayaa] ERROR: PostgreSQL is required but not running at ${host}:${port}." >&2
  echo "[anayaa] Run: ./scripts/setup_postgres.sh" >&2
  exit 1
}

ensure_redis() {
<<<<<<< HEAD
  local url="${REDIS_URL:-redis://127.0.0.1:6379/0}"
=======
  local url="${REDIS_URL:-redis://localhost:6379/0}"
>>>>>>> origin/main
  if python - "$url" <<'PY'
import sys
from urllib.parse import urlparse
import redis

url = sys.argv[1]
parsed = urlparse(url)
<<<<<<< HEAD
client = redis.Redis(host=parsed.hostname or "127.0.0.1", port=parsed.port or 6379, db=int((parsed.path or "/0").lstrip("/") or 0))
=======
client = redis.Redis(host=parsed.hostname or "localhost", port=parsed.port or 6379, db=int((parsed.path or "/0").lstrip("/") or 0))
>>>>>>> origin/main
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
    python scripts/seed_milvus.py
  elif [[ $status -ne 0 ]]; then
    exit "$status"
  fi
}

main() {
  log "Anayaa.AI backend startup"
  ensure_venv
  load_env
  ensure_ollama || true
  ensure_postgres
  ensure_redis
  ensure_milvus
  cd "$BACKEND"
  unset MILVUS_URI
  log "Starting FastAPI at http://localhost:8000"
  exec uvicorn app.main:app --reload --port 8000
}

main "$@"
