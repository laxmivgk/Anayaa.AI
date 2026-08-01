#!/usr/bin/env bash
# Install the local Anayaa CLI wrapper for technical public-beta users.
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" >/dev/null 2>&1 && pwd -P || pwd)"
ROOT=""
if [[ -x "$SCRIPT_DIR/anayaa" && -d "$SCRIPT_DIR/../backend" && -d "$SCRIPT_DIR/../frontend" ]]; then
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

BIN_DIR="${ANAYAA_BIN_DIR:-$HOME/.local/bin}"
TARGET="$BIN_DIR/anayaa"
INSTALL_DIR="${ANAYAA_INSTALL_DIR:-$HOME/.anayaa/Anayaa.AI}"
DEFAULT_RELEASE_URL="https://github.com/laxmivgk/Anayaa.AI/archive/refs/tags/v0.1.6-local-beta.tar.gz"
RELEASE_URL="${ANAYAA_RELEASE_URL:-$DEFAULT_RELEASE_URL}"
REPLACE_INSTALL=false
INSTALL_SYSTEM_DEPS="${ANAYAA_INSTALL_SYSTEM_DEPS:-true}"

log() { echo "[anayaa-install] $*"; }
warn() { echo "[anayaa-install] WARNING: $*" >&2; }
fail() { echo "[anayaa-install] ERROR: $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  ./scripts/install-anayaa.sh [options]
  curl -sSL <release-install-url> | bash

Installs the `anayaa` command. From a checkout, this links to scripts/anayaa.
When run through curl, it downloads a release archive into ~/.anayaa/Anayaa.AI.
Rerunning a release install updates Anayaa code while preserving local runtime state.

Options:
  --bin-dir DIR     Install the command link in DIR instead of ~/.local/bin
  --install-dir DIR Install downloaded release files in DIR instead of ~/.anayaa/Anayaa.AI
  --release-url URL Download this release archive when not running from a checkout
  --replace         Replace an existing downloaded install directory without preserving local runtime state
  --no-system-deps  Do not install/start system dependencies; only check them
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
    --install-dir)
      [[ "$#" -ge 2 ]] || fail "--install-dir requires a directory"
      INSTALL_DIR="$2"
      shift 2
      ;;
    --release-url)
      [[ "$#" -ge 2 ]] || fail "--release-url requires a URL"
      RELEASE_URL="$2"
      shift 2
      ;;
    --replace)
      REPLACE_INSTALL=true
      shift
      ;;
    --no-system-deps)
      INSTALL_SYSTEM_DEPS=false
      shift
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
  brew install python node postgresql redis ollama
  brew services start postgresql
  brew services start redis
  ollama serve

Ubuntu / WSL2:
  sudo apt update
  sudo apt install -y curl build-essential python3 python3-venv python3-pip nodejs npm postgresql redis-server
  sudo service postgresql start
  sudo service redis-server start
  curl -fsSL https://ollama.com/install.sh | sh
  ollama serve

Ollama install docs:
  https://ollama.com
EOF
}

run_privileged() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
    return $?
  fi

  if command -v sudo >/dev/null 2>&1; then
    sudo "$@"
    return $?
  fi

  "$@"
}

postgres_reachable() {
  command -v pg_isready >/dev/null 2>&1 && pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1
}

redis_reachable() {
  command -v redis-cli >/dev/null 2>&1 && redis-cli -u redis://127.0.0.1:6379/0 ping >/dev/null 2>&1
}

ollama_reachable() {
  command -v curl >/dev/null 2>&1 && curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1
}

wait_for_service() {
  local check_name="$1"
  for _ in $(seq 1 20); do
    "$check_name" && return 0
    sleep 1
  done
  return 1
}

brew_formula_installed() {
  local formula="$1"
  command -v brew >/dev/null 2>&1 && brew list --versions "$formula" >/dev/null 2>&1
}

start_homebrew_postgres() {
  local formulas=(postgresql@18 postgresql@17 postgresql@16 postgresql@15 postgresql@14 postgresql)
  local formula
  for formula in "${formulas[@]}"; do
    if brew_formula_installed "$formula"; then
      log "Starting PostgreSQL with Homebrew service: $formula"
      brew services start "$formula" >/dev/null 2>&1 || true
      wait_for_service postgres_reachable && return 0
    fi
  done
  return 1
}

start_homebrew_redis() {
  if brew_formula_installed redis; then
    log "Starting Redis with Homebrew service: redis"
    brew services start redis >/dev/null 2>&1 || true
    wait_for_service redis_reachable && return 0
  fi
  return 1
}

start_ollama_if_possible() {
  if ollama_reachable; then
    log "OK: Ollama API reachable at http://127.0.0.1:11434"
    return 0
  fi

  if command -v ollama >/dev/null 2>&1; then
    log "Starting Ollama in the background..."
    nohup ollama serve >> "$HOME/.anayaa/ollama-serve.log" 2>&1 &
    wait_for_service ollama_reachable && return 0
  fi

  return 1
}

install_macos_system_deps() {
  if ! command -v brew >/dev/null 2>&1; then
    fail "Homebrew is required for one-command macOS setup. Install it from https://brew.sh, then rerun this installer."
  fi

  local formulas=()
  command -v python3 >/dev/null 2>&1 || formulas+=(python)
  if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    formulas+=(node)
  fi
  command -v pg_isready >/dev/null 2>&1 || formulas+=(postgresql)
  command -v redis-cli >/dev/null 2>&1 || formulas+=(redis)
  command -v ollama >/dev/null 2>&1 || formulas+=(ollama)

  if [[ "${#formulas[@]}" -gt 0 ]]; then
    log "Installing missing macOS dependencies with Homebrew: ${formulas[*]}"
    brew install "${formulas[@]}"
  fi

  if ! postgres_reachable; then
    start_homebrew_postgres || warn "PostgreSQL is installed but not reachable yet. `anayaa setup` will retry and print recovery steps if needed."
  else
    log "OK: PostgreSQL reachable at 127.0.0.1:5432"
  fi

  if ! redis_reachable; then
    start_homebrew_redis || warn "Redis is installed but not reachable yet. `anayaa setup` will retry and print recovery steps if needed."
  else
    log "OK: Redis reachable at redis://127.0.0.1:6379/0"
  fi

  start_ollama_if_possible || warn "Ollama CLI is installed but the API is not reachable yet. Run `ollama serve` if `anayaa setup` cannot reach it."
}

install_linux_system_deps() {
  local needs_apt=false
  for command_name in curl python3 node npm pg_isready redis-cli; do
    command -v "$command_name" >/dev/null 2>&1 || needs_apt=true
  done

  # Keep the beta install close to an Ollama-style one-command setup while
  # still using the platform package manager for standard Linux services.
  if [[ "$needs_apt" == true ]] && command -v apt-get >/dev/null 2>&1; then
    log "Installing missing Linux dependencies with apt."
    run_privileged apt-get update
    run_privileged apt-get install -y curl build-essential python3 python3-venv python3-pip nodejs npm postgresql redis-server
  elif [[ "$needs_apt" == true ]]; then
    warn "Automatic Linux dependency installation currently supports apt-based systems. Install Python, Node.js, PostgreSQL, Redis, and Ollama manually, then rerun."
  fi

  if command -v service >/dev/null 2>&1; then
    run_privileged service postgresql start >/dev/null 2>&1 || true
    run_privileged service redis-server start >/dev/null 2>&1 || true
  elif command -v systemctl >/dev/null 2>&1; then
    run_privileged systemctl start postgresql >/dev/null 2>&1 || true
    run_privileged systemctl start redis-server >/dev/null 2>&1 || true
  fi

  # Ollama is not an Ubuntu apt package; use the official installer so Linux
  # and WSL users get the same runtime dependency the macOS Homebrew path gives.
  ensure_linux_ollama
  start_ollama_if_possible || warn "Ollama CLI is installed but the API is not reachable yet. Run `ollama serve` if `anayaa setup` cannot reach it."
}

ensure_linux_ollama() {
  if command -v ollama >/dev/null 2>&1; then
    return 0
  fi

  if ! command -v curl >/dev/null 2>&1; then
    warn "Ollama is not installed and curl is unavailable. Install Ollama from https://ollama.com/download, then rerun this installer."
    return 1
  fi

  if [[ "$(id -u)" -ne 0 ]] && ! command -v sudo >/dev/null 2>&1; then
    warn "Ollama is not installed and sudo is unavailable. Install Ollama from https://ollama.com/download, then rerun this installer."
    return 1
  fi

  log "Installing Ollama from official installer: https://ollama.com/install.sh"
  if curl -fsSL https://ollama.com/install.sh | sh; then
    return 0
  fi

  warn "Ollama automatic install failed. Install from https://ollama.com/download, then rerun this installer."
  return 1
}

ensure_system_deps() {
  if [[ "$INSTALL_SYSTEM_DEPS" != "true" ]]; then
    log "Skipping automatic system dependency installation because --no-system-deps was provided."
    return 0
  fi

  case "$(detect_os)" in
    macOS) install_macos_system_deps ;;
    Linux|WSL/Linux) install_linux_system_deps ;;
    *) warn "Unsupported platform for automatic system dependency installation. Install prerequisites manually." ;;
  esac
}

resolve_root() {
  if [[ -n "$ROOT" ]]; then
    return 0
  fi

  if [[ -d "$INSTALL_DIR" && -x "$INSTALL_DIR/scripts/anayaa" ]]; then
    if [[ -n "$RELEASE_URL" ]]; then
      log "Updating existing Anayaa install at: $INSTALL_DIR"
      download_release
      return 0
    fi
    ROOT="$(cd "$INSTALL_DIR" && pwd)"
    log "Using existing Anayaa install at: $ROOT"
    return 0
  fi

  [[ -n "$RELEASE_URL" ]] || fail "No checkout detected. Re-run with --release-url URL or set ANAYAA_RELEASE_URL to an Anayaa release archive."
  download_release
}

preserve_path_if_present() {
  local preserve_dir="$1"
  local relative_path="$2"
  local source_path="$INSTALL_DIR/$relative_path"

  [[ -e "$source_path" ]] || return 0
  mkdir -p "$preserve_dir/$(dirname "$relative_path")"
  cp -a "$source_path" "$preserve_dir/$relative_path"
}

preserve_install_state() {
  local preserve_dir="$1"
  [[ -d "$INSTALL_DIR" ]] || return 0

  preserve_path_if_present "$preserve_dir" "backend/.env"
  preserve_path_if_present "$preserve_dir" "backend/data"
  preserve_path_if_present "$preserve_dir" "backend/anayaa"
  preserve_path_if_present "$preserve_dir" "frontend/node_modules"
  preserve_path_if_present "$preserve_dir" ".ollama-serve.log"
}

restore_path_if_present() {
  local preserve_dir="$1"
  local relative_path="$2"
  local preserved_path="$preserve_dir/$relative_path"

  [[ -e "$preserved_path" ]] || return 0
  mkdir -p "$INSTALL_DIR/$(dirname "$relative_path")"
  rm -rf "$INSTALL_DIR/$relative_path"
  cp -a "$preserved_path" "$INSTALL_DIR/$relative_path"
}

restore_install_state() {
  local preserve_dir="$1"
  [[ -d "$preserve_dir" ]] || return 0

  restore_path_if_present "$preserve_dir" "backend/.env"
  restore_path_if_present "$preserve_dir" "backend/data"
  restore_path_if_present "$preserve_dir" "backend/anayaa"
  restore_path_if_present "$preserve_dir" "frontend/node_modules"
  restore_path_if_present "$preserve_dir" ".ollama-serve.log"
}

download_release() {
  command -v curl >/dev/null 2>&1 || fail "curl is required to download Anayaa"
  command -v tar >/dev/null 2>&1 || fail "tar is required to extract Anayaa"

  if [[ -e "$INSTALL_DIR" ]]; then
    if [[ "$INSTALL_DIR" != "$HOME/.anayaa/Anayaa.AI" && "$INSTALL_DIR" != "$HOME"/.anayaa/* ]]; then
      fail "Updating or replacing an existing install is only allowed inside ~/.anayaa for safety: $INSTALL_DIR"
    fi
  fi

  local tmp_dir archive extract_dir preserve_dir source_dir
  tmp_dir="$(mktemp -d)"
  ANAYAA_INSTALL_TMP_DIR="$tmp_dir"
  archive="$tmp_dir/anayaa-release.archive"
  extract_dir="$tmp_dir/extract"
  preserve_dir="$tmp_dir/preserve"
  mkdir -p "$extract_dir"
  trap 'rm -rf "${ANAYAA_INSTALL_TMP_DIR:-}"' EXIT

  log "Downloading Anayaa release archive..."
  curl -fL "$RELEASE_URL" -o "$archive"

  log "Extracting Anayaa release..."
  if ! tar -xzf "$archive" -C "$extract_dir" >/dev/null 2>&1; then
    if command -v unzip >/dev/null 2>&1; then
      unzip -q "$archive" -d "$extract_dir" || fail "Could not extract release archive"
    else
      fail "Could not extract release archive. Use a .tar.gz release, or install unzip."
    fi
  fi

  source_dir="$(find "$extract_dir" -maxdepth 3 -type f -path '*/scripts/anayaa' -print -quit | sed 's|/scripts/anayaa$||')"
  [[ -n "$source_dir" ]] || fail "Release archive did not contain scripts/anayaa"

  if [[ "$REPLACE_INSTALL" != true ]]; then
    preserve_install_state "$preserve_dir"
  fi

  mkdir -p "$(dirname "$INSTALL_DIR")"
  if [[ -e "$INSTALL_DIR" ]]; then
    rm -rf "$INSTALL_DIR"
  fi
  mv "$source_dir" "$INSTALL_DIR"
  if [[ "$REPLACE_INSTALL" != true ]]; then
    restore_install_state "$preserve_dir"
  fi
  ROOT="$(cd "$INSTALL_DIR" && pwd)"
  log "Installed Anayaa files at: $ROOT"
}

check_wsl_install_path() {
  if grep -qi microsoft /proc/version 2>/dev/null && [[ "$ROOT" == /mnt/* ]]; then
    warn "Anayaa is installed under /mnt. WSL users should install under the Linux filesystem, for example ~/Anayaa.AI or ~/.anayaa/Anayaa.AI."
  fi
}

check_script_bits() {
  local script
  for script in "$ROOT/scripts/anayaa" "$ROOT/scripts/setup-online.sh" "$ROOT/scripts/setup_postgres.sh" "$ROOT/scripts/start-backend.sh" "$ROOT/scripts/free-resources.sh"; do
    [[ -f "$script" ]] || fail "Missing expected script: $script"
    chmod +x "$script" 2>/dev/null || true
  done
}

main() {
  resolve_root
  log "Installing Anayaa local CLI from: $ROOT"
  log "Detected platform: $(detect_os)"
  check_wsl_install_path
  ensure_system_deps

  local missing=false
  for command_name in curl python3 node npm pg_isready redis-cli ollama; do
    check_command "$command_name" || missing=true
  done

  if [[ "$missing" == true ]]; then
    print_dependency_help
    exit 1
  fi

  check_script_bits

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
