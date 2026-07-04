#!/usr/bin/env bash
# Install the local Anayaa CLI wrapper for technical public-beta users.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${ANAYAA_BIN_DIR:-$HOME/.local/bin}"
TARGET="$BIN_DIR/anayaa"

log() { echo "[anayaa-install] $*"; }
warn() { echo "[anayaa-install] WARNING: $*" >&2; }
fail() { echo "[anayaa-install] ERROR: $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: ./scripts/install-anayaa.sh [options]

Installs the `anayaa` command by linking it to this checkout's scripts/anayaa entrypoint.

Options:
  --bin-dir DIR     Install the command link in DIR instead of ~/.local/bin
  --check-only      Check prerequisites and print next steps without creating the command link
  --help            Show this help

After install:
  anayaa setup
  anayaa serve
EOF
}

CHECK_ONLY=false

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --bin-dir)
      [[ "$#" -ge 2 ]] || fail "--bin-dir requires a directory"
      BIN_DIR="$2"
      TARGET="$BIN_DIR/anayaa"
      shift 2
      ;;
    --check-only)
      CHECK_ONLY=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      ;;
  esac
done

detect_os() {
  local kernel
  kernel="$(uname -s)"
  case "$kernel" in
    Darwin) echo "macOS" ;;
    Linux)
      if grep -qi microsoft /proc/version 2>/dev/null; then
        echo "WSL/Linux"
      else
        echo "Linux"
      fi
      ;;
    *) echo "$kernel" ;;
  esac
}

check_command() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    log "OK: found $name"
    return 0
  fi
  warn "Missing: $name"
  return 1
}

print_dependency_help() {
  cat <<'EOF'

Install missing dependencies, then rerun this installer.

macOS:
  brew install python node postgresql@16 redis ollama
  brew services start postgresql@16
  brew services start redis
  ollama serve

Ubuntu / WSL2:
  sudo apt update
  sudo apt install -y git curl build-essential python3 python3-venv python3-pip nodejs npm postgresql redis-server
  sudo service postgresql start
  sudo service redis-server start
  ollama serve

Ollama install docs:
  https://ollama.com
EOF
}

main() {
  log "Installing Anayaa local CLI from: $ROOT"
  log "Detected platform: $(detect_os)"

  local missing=false
  for command_name in git curl python3 node npm; do
    check_command "$command_name" || missing=true
  done

  if ! check_command ollama; then
    missing=true
  fi

  if [[ "$missing" == true ]]; then
    print_dependency_help
    exit 1
  fi

  if [[ "$CHECK_ONLY" == true ]]; then
    log "Check-only mode complete."
    exit 0
  fi

  mkdir -p "$BIN_DIR"
  ln -sfn "$ROOT/scripts/anayaa" "$TARGET"
  chmod +x "$ROOT/scripts/anayaa"

  log "Installed command: $TARGET"
  if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    warn "$BIN_DIR is not currently on PATH."
    warn "Add this line to your shell profile:"
    echo "export PATH=\"$BIN_DIR:\$PATH\""
  fi

  cat <<EOF

Next steps:
  anayaa setup
  anayaa doctor
  anayaa serve

Open:
  http://127.0.0.1:8000
EOF
}

main "$@"
