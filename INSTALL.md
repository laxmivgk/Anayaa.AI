# Install Anayaa Locally

Anayaa is distributed as a local-first app. The app runs on your machine, and your browser talks to a local server at `http://127.0.0.1:8000`.

## Quick Start

Public release install:

```bash
curl -sSL https://raw.githubusercontent.com/laxmivgk/Anayaa.AI/v0.1.1-local-beta/scripts/install-anayaa.sh | bash
anayaa setup
anayaa serve
```

Open:

```text
http://127.0.0.1:8000
```

Developer checkout install:

```bash
git clone <anayaa-repo-url>
cd Anayaa.AI
./scripts/install-anayaa.sh
anayaa setup
anayaa serve
```

The release installer downloads Anayaa into `~/.anayaa/Anayaa.AI`, links the `anayaa` command into `~/.local/bin`, and attempts to install/start required local system services where the platform has a supported package manager. On macOS it uses Homebrew for Python, Node.js, PostgreSQL, Redis, and Ollama. On apt-based Linux/WSL it installs Python, Node.js, PostgreSQL, Redis, and Ollama; Ollama is installed from the official `https://ollama.com/install.sh` script when missing. If your shell cannot find `anayaa` after install, add `~/.local/bin` to `PATH` or run the printed command from the installer output.

## What Setup Does

`anayaa setup` is the one-time online app setup. Keep Wi-Fi on for this step. It prepares the Anayaa PostgreSQL role/database, installs backend and frontend dependencies, builds the frontend, pulls required Ollama models, caches embedding assets, exports local ONNX embeddings, and seeds scripture retrieval. Run it again after updating `backend/data/scriptures.json`; setup checks the stored corpus count and checksum, then rebuilds Milvus embeddings when the corpus changed.

After setup, normal runtime is local/offline-first:

```bash
anayaa serve
```

## Requirements

- Python 3.10+
- Node.js 18+
- PostgreSQL
- Redis
- Ollama
- Enough disk space for Python packages, npm packages, Ollama models, ONNX embedding assets, and Milvus Lite data

## macOS

The public release installer attempts these Homebrew steps for you. If you need to repair prerequisites manually, run:

```bash
brew install python node postgresql redis ollama
brew services start postgresql
brew services start redis
ollama serve
```

Then rerun:

```bash
anayaa setup
anayaa serve
```

## Linux

The public release installer attempts the apt steps below on Ubuntu/WSL. If you need to repair prerequisites manually, run:

```bash
sudo apt update
sudo apt install -y curl build-essential python3 python3-venv python3-pip nodejs npm postgresql redis-server
sudo service postgresql start
sudo service redis-server start
curl -fsSL https://ollama.com/install.sh | sh
```

Then run:

```bash
ollama serve
anayaa setup
anayaa serve
```

## Windows

The supported technical-beta Windows path is WSL2 Ubuntu.

In PowerShell as Administrator:

```powershell
wsl --install -d Ubuntu
```

Then open Ubuntu and run the Linux steps above inside WSL. Keep Anayaa inside the WSL filesystem, for example under `~/.anayaa/Anayaa.AI` or `~/Anayaa.AI`, rather than under `/mnt/c/...`. Windows-mounted paths can cause shell permission, line-ending, virtualenv, and Milvus Lite socket problems.

If setup reports PostgreSQL role or database access errors, run:

```bash
sudo service postgresql start
sudo -u postgres psql -d postgres -c "ALTER ROLE anayaa WITH LOGIN PASSWORD 'anayaa_dev';"
anayaa setup
```

## Daily Use

Start Anayaa:

```bash
anayaa serve
```

Check the installation:

```bash
anayaa doctor
```

Stop local app processes:

```bash
anayaa stop
```

Safe cleanup:

```bash
anayaa clean
```

Full reset cleanup:

```bash
anayaa clean --all --yes
```

After a full reset, reconnect to Wi-Fi and run:

```bash
anayaa setup
```

## Local-First Defaults

- Anayaa binds to `127.0.0.1` by default.
- The frontend is served locally.
- PostgreSQL, Redis, Milvus Lite, embeddings, scripture data, and Ollama models are local.
- Cloud LLM routing is disabled unless you explicitly configure a cloud key such as `GEMINI_API_KEY`.
- No public server is required for normal local use.

Password reset is server-side. In local mode without SMTP, reset instructions are printed to the backend terminal. In production, set `APP_ENV=production` and configure SMTP so reset links/codes are delivered by email; terminal-only reset delivery is refused. Users must enter an email that already exists in Anayaa to receive usable reset instructions.

## Troubleshooting

Run:

```bash
anayaa doctor
```

If a dependency is missing, install or start the named service, then rerun:

```bash
anayaa setup
```

If Anayaa still shows an old response or old UI text, restart the local server:

```bash
anayaa stop
anayaa serve
```
