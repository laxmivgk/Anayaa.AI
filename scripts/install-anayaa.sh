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
DEFAULT_RELEASE_URL="https://github.com/laxmivgk/Anayaa.AI/archive/refs/tags/v0.1.0-local-beta.tar.gz"
RELEASE_URL="${ANAYAA_RELEASE_URL:-$DEFAULT_RELEASE_URL}"
REPLACE_INSTALL=false

log() { echo "[anayaa-install] $*"; }
warn() { echo "[anayaa-install] WARNING: $*" >&2; }
fail() { echo "[anayaa-install] ERROR: $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  ./scripts/install-anayaa.sh [options]
  curl -sSL <release-install-url> | bash

Installs the `anayaa` command. From a checkout, this links to scripts/anayaa.
When run through curl, it downloads a release archive and installs it under ~/.anayaa/Anayaa.AI.

Options:
  --bin-dir DIR     Install the command link in DIR instead of ~/.local/bin
  --install-dir DIR Install downloaded release files in DIR instead of ~/.anayaa/Anayaa.AI
  --release-url URL Download this release archive when not running from a checkout
  --replace         Replace an existing downloaded install directory
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

check_optional_command() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    log "OK: found $name"
    return 0
  fi
  warn "Missing optional runtime dependency: $name"
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
  sudo apt install -y curl build-essential python3 python3-venv python3-pip nodejs npm postgresql redis-server
  sudo service postgresql start
  sudo service redis-server start
  ollama serve

Ollama install docs:
  https://ollama.com
EOF
}

resolve_root() {
  if [[ -n "$ROOT" ]]; then
    return 0
  fi

  if [[ -d "$INSTALL_DIR" && -x "$INSTALL_DIR/scripts/anayaa" ]]; then
    ROOT="$(cd "$INSTALL_DIR" && pwd)"
    log "Using existing Anayaa install at: $ROOT"
    return 0
  fi

  [[ -n "$RELEASE_URL" ]] || fail "No checkout detected. Re-run with --release-url URL or set ANAYAA_RELEASE_URL to an Anayaa release archive."
  download_release
}

download_release() {
  command -v curl >/dev/null 2>&1 || fail "curl is required to download Anayaa"
  command -v tar >/dev/null 2>&1 || fail "tar is required to extract Anayaa"

  if [[ -e "$INSTALL_DIR" ]]; then
    if [[ "$REPLACE_INSTALL" != true ]]; then
      fail "Install directory already exists: $INSTALL_DIR. Re-run with --replace to replace it, or set ANAYAA_INSTALL_DIR."
    fi
    if [[ "$INSTALL_DIR" != "$HOME/.anayaa/Anayaa.AI" && "$INSTALL_DIR" != "$HOME"/.anayaa/* ]]; then
      fail "--replace is only allowed inside ~/.anayaa for safety: $INSTALL_DIR"
    fi
  fi

  local tmp_dir archive extract_dir source_dir
  tmp_dir="$(mktemp -d)"
  ANAYAA_INSTALL_TMP_DIR="$tmp_dir"
  archive="$tmp_dir/anayaa-release.archive"
  extract_dir="$tmp_dir/extract"
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

  mkdir -p "$(dirname "$INSTALL_DIR")"
  if [[ -e "$INSTALL_DIR" ]]; then
    rm -rf "$INSTALL_DIR"
  fi
  mv "$source_dir" "$INSTALL_DIR"
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

  local missing=false
  for command_name in curl python3 node npm; do
    check_command "$command_name" || missing=true
  done

  check_optional_command git || true
  check_optional_command pg_isready || true
  check_optional_command redis-cli || true

  if ! check_command ollama; then
    missing=true
  fi

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
