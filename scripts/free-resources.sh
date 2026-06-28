#!/usr/bin/env bash
# Stop Anayaa.AI local processes and optionally clean local resources/storage.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"

STOP_SERVICES=false
WIPE_STORAGE=false
REMOVE_DEPS=false
ASSUME_YES=false

usage() {
  cat <<'EOF'
Usage: ./scripts/free-resources.sh [options]

Default behavior:
  - Stop Anayaa app processes on local app ports
  - Stop orphaned Anayaa uvicorn/Vite/MCP child processes
  - Remove generated caches, .DS_Store files, local logs, and frontend build output

Options:
  --services   Also stop shared local services on configured ports:
               PostgreSQL, Redis, Ollama, standalone Milvus
  --storage    Also wipe app storage:
               Redis DB, Anayaa PostgreSQL tables, Milvus Lite DB
  --deps       Also remove dependency folders:
               backend/.venv, legacy local venvs, frontend/node_modules
  --all        Enable --services --storage --deps
  --yes        Skip confirmation prompts for --services/--storage
  --help       Show this help

Examples:
  ./scripts/free-resources.sh
  ./scripts/free-resources.sh --services
  ./scripts/free-resources.sh --storage
  ./scripts/free-resources.sh --all --yes
EOF
}

for arg in "$@"; do
  case "$arg" in
    --services) STOP_SERVICES=true ;;
    --storage) WIPE_STORAGE=true ;;
    --deps) REMOVE_DEPS=true ;;
    --all)
      STOP_SERVICES=true
      WIPE_STORAGE=true
      REMOVE_DEPS=true
      ;;
    --yes) ASSUME_YES=true ;;
    --help) usage; exit 0 ;;
    *) echo "[anayaa] Unknown option: $arg" >&2; usage; exit 1 ;;
  esac
done

log() { echo "[anayaa] $*"; }
warn() { echo "[anayaa] WARNING: $*" >&2; }

confirm() {
  local prompt="$1"
  if [[ "$ASSUME_YES" == true ]]; then
    return 0
  fi
  local answer
  read -r -p "[anayaa] ${prompt} Type 'yes' to continue: " answer
  [[ "$answer" == "yes" ]]
}

load_env() {
  if [[ -f "$BACKEND/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$BACKEND/.env"
    set +a
  fi
}

pids_on_port() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true
}

stop_pids() {
  local label="$1"
  shift
  local pids=("$@")
  if [[ "${#pids[@]}" -eq 0 ]]; then
    return 0
  fi

  log "Stopping ${label}: ${pids[*]}"
  kill "${pids[@]}" 2>/dev/null || true
  sleep 1

  local alive=()
  local pid
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      alive+=("$pid")
    fi
  done
  if [[ "${#alive[@]}" -gt 0 ]]; then
    warn "Force stopping ${label}: ${alive[*]}"
    kill -9 "${alive[@]}" 2>/dev/null || true
  fi
}

stop_port() {
  local label="$1"
  local port="$2"
  local pids=()
  local pid
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && pids+=("$pid")
  done < <(pids_on_port "$port")
  stop_pids "${label} port ${port}" "${pids[@]}"
}

stop_port_if_matching() {
  local label="$1"
  local port="$2"
  local pattern="$3"
  local pids=()
  local pid
  local command
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$command" =~ $pattern ]]; then
      pids+=("$pid")
    else
      warn "Skipped ${label} port ${port}; pid ${pid} does not look like an Anayaa process."
    fi
  done < <(pids_on_port "$port")
  stop_pids "${label} port ${port}" "${pids[@]}"
}

stop_matching_processes() {
  local label="$1"
  local pattern="$2"
  local pids=()
  local pid
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && pids+=("$pid")
  done < <(pgrep -f "$pattern" 2>/dev/null | awk -v self="$$" '$1 != self' | sort -u || true)
  stop_pids "$label" "${pids[@]}"
}

clean_generated() {
  log "Cleaning generated caches and build output..."
  find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
  find "$ROOT" -type d -name .pytest_cache -prune -exec rm -rf {} +
  find "$ROOT" -type d -name .vite -prune -exec rm -rf {} +
  find "$ROOT" -name .DS_Store -exec rm -f {} +
  rm -rf "$ROOT/frontend/dist"
  rm -rf "$ROOT/frontend/node_modules/.vite"
  rm -f "$ROOT/.ollama-serve.log"
}

remove_deps() {
  log "Removing dependency folders..."
  rm -rf "$ROOT/backend/.venv"
  rm -rf "$ROOT/backend/anayaa"
  rm -rf "$ROOT/Anayaa"
  rm -rf "$ROOT/frontend/node_modules"
}

wipe_redis() {
  local url="${REDIS_URL:-redis://localhost:6379/0}"
  if ! command -v redis-cli >/dev/null 2>&1; then
    warn "redis-cli not found; skipped Redis cleanup."
    return 0
  fi
  if redis-cli -u "$url" ping >/dev/null 2>&1; then
    log "Flushing Redis DB at ${url}..."
    redis-cli -u "$url" FLUSHDB >/dev/null
  else
    warn "Redis not reachable at ${url}; skipped Redis cleanup."
  fi
}

wipe_postgres() {
  if ! command -v psql >/dev/null 2>&1; then
    warn "psql not found; skipped PostgreSQL cleanup."
    return 0
  fi

  local host="${POSTGRES_HOST:-localhost}"
  local port="${POSTGRES_PORT:-5432}"
  local db="${POSTGRES_DB:-anayaa}"
  local user="${POSTGRES_USER:-anayaa}"
  local password="${POSTGRES_PASSWORD:-anayaa_dev}"

  log "Clearing Anayaa PostgreSQL tables in ${db} at ${host}:${port}..."
  PGPASSWORD="$password" psql \
    -h "$host" \
    -p "$port" \
    -U "$user" \
    -d "$db" \
    -v ON_ERROR_STOP=1 \
    >/dev/null <<'SQL'
DO $$
DECLARE
  table_names text[] := ARRAY[
    'hitl_checkpoints',
    'audit_logs',
    'daily_eco_rollups',
    'request_eco_metrics',
    'feedback_records',
    'agent_traces',
    'turns',
    'sessions',
    'kg_edges',
    'kg_entities',
    'scriptures'
  ];
  existing_tables text;
BEGIN
  SELECT string_agg(format('%I', table_name), ', ')
    INTO existing_tables
  FROM information_schema.tables
  WHERE table_schema = 'public'
    AND table_name = ANY(table_names);

  IF existing_tables IS NOT NULL THEN
    EXECUTE 'TRUNCATE TABLE ' || existing_tables || ' RESTART IDENTITY CASCADE';
  END IF;

  IF to_regclass('public.corpus_status') IS NOT NULL THEN
    UPDATE corpus_status
    SET ready = FALSE,
        verse_count = 0,
        last_seed_at = NULL,
        seed_version = NULL,
        seed_checksum = NULL
    WHERE id = 1;
  END IF;
END $$;
SQL
}

wipe_milvus_lite() {
  local uri="${ANAYAA_MILVUS_URI:-data/milvus.db}"
  local path="$uri"
  if [[ "$uri" != /* ]]; then
    path="$BACKEND/$uri"
  fi
  if [[ "$path" == *.db ]]; then
    log "Removing Milvus Lite files at ${path}..."
    rm -rf "$path" "$path-shm" "$path-wal" "$path.lock"
  else
    warn "ANAYAA_MILVUS_URI is not a local .db path (${uri}); skipped Milvus file cleanup."
  fi
}

stop_app_processes() {
  log "Stopping Anayaa app processes..."
  stop_port_if_matching "FastAPI" "${FASTAPI_PORT:-8000}" "$ROOT/backend|uvicorn app.main:app"
  stop_port_if_matching "isolated FastAPI smoke-test" "8001" "$ROOT/backend|uvicorn app.main:app"
  stop_port_if_matching "Vite frontend" "${FRONTEND_PORT:-5173}" "$ROOT/frontend|vite"
  stop_port_if_matching "alternate Vite frontend" "5174" "$ROOT/frontend|vite"
  stop_matching_processes "Anayaa MCP retrieval server" "$ROOT/backend/app/mcp/milvus_retrieval_server.py"
  stop_matching_processes "Anayaa uvicorn process" "$ROOT/backend.*uvicorn|uvicorn app.main:app"
  stop_matching_processes "Anayaa Vite process" "$ROOT/frontend.*vite|vite --host|vite$"
}

stop_shared_services() {
  if ! confirm "This can stop shared local PostgreSQL, Redis, Ollama, and Milvus services."; then
    log "Skipped shared service shutdown."
    return 0
  fi

  log "Stopping shared local services by port..."
  stop_port "PostgreSQL" "${POSTGRES_PORT:-5432}"
  stop_port "Redis" "${REDIS_PORT:-6379}"
  stop_port "Ollama" "${OLLAMA_PORT:-11434}"
  stop_port "Milvus gRPC" "${MILVUS_GRPC_PORT:-19530}"
  stop_port "Milvus HTTP" "${MILVUS_HTTP_PORT:-9091}"
}

wipe_storage() {
  if ! confirm "This will wipe Anayaa Redis/PostgreSQL app data and local Milvus Lite files."; then
    log "Skipped storage cleanup."
    return 0
  fi

  wipe_redis
  wipe_postgres || warn "PostgreSQL cleanup failed; check service status and credentials."
  wipe_milvus_lite
}

main() {
  load_env
  stop_app_processes
  clean_generated

  if [[ "$WIPE_STORAGE" == true ]]; then
    wipe_storage
  fi

  if [[ "$REMOVE_DEPS" == true ]]; then
    remove_deps
  fi

  if [[ "$STOP_SERVICES" == true ]]; then
    stop_shared_services
  fi

  log "Resource cleanup complete."
}

main "$@"
