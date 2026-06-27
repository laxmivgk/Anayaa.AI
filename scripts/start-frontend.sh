#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/frontend"

if [[ ! -d node_modules ]]; then
  npm install
fi

<<<<<<< HEAD
exec npm run dev -- --host 127.0.0.1
=======
exec npm run dev
>>>>>>> origin/main
