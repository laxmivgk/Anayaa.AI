# Anayaa.AI Runbook

This README is a compact implementation and execution guide for Anayaa.AI. The main project README explains the product and API in more depth; this file focuses on reproducible local setup, hardware, software, side effects, and assumptions.

## Problem

People often ask moral or life-guidance questions and receive generic answers that are not grounded, transparent, or safe. Anayaa.AI addresses this by taking a user dilemma, retrieving scripture evidence, generating local LLM guidance, judging the result, and refusing to show unsupported guidance.

## Solution

Anayaa.AI is a local-first FastAPI and React app that:

- Sanitizes and PII-scrubs user input.
- Blocks prompt-injection and dangerous patterns.
- Uses an LLM planner to choose retrieval concepts.
- Retrieves scripture through an MCP boundary backed by Milvus Lite.
- Generates guidance with a local Ollama model.
- Runs an LLM judge plus deterministic grounding contract.
- Returns citations, a user-facing "Why this guidance?" section, latency metrics, eco metrics, and explicit failure states.

## Architecture

```text
React/Vite frontend
  -> FastAPI backend
    -> auth, session, rate-limit, sanitizer, firewall, PII scrubber
    -> Google ADK workflow
      -> query optimizer
      -> LLM planner: gemma2:2b
      -> ReAct retry planner: gemma2:2b
      -> MCP stdio retrieval client
        -> MCP Milvus server
          -> milvus_hybrid_search
          -> graph_expand
          -> rerank_candidates_tool
      -> LLM synthesizer: llama3.2:3b
      -> LLM judge: llama3.2:3b
      -> grounding contract and cache policy
    -> PostgreSQL, Redis, Milvus Lite
```

## Hardware Used

Observed local development machine:

| Item | Value |
| --- | --- |
| Machine | Mac mini |
| Chip / CPU | Apple M1 |
| CPU cores | 8 total: 4 performance, 4 efficiency |
| Memory | 8 GB |
| GPU | Integrated Apple M1 GPU |
| GPU cores | 8 |
| Number of GPUs | 1 integrated GPU |

## OS / Platform

| Item | Value |
| --- | --- |
| OS | macOS |
| Version | 26.3 |
| Build | 25D125 |
| Kernel | Darwin 25.3.0 |
| Architecture | arm64 |

## Third-Party Software

Observed local versions:

| Software | Version | Purpose |
| --- | --- | --- |
| Python | 3.10.5 in `backend/anayaa` | Backend runtime |
| Node.js | 25.9.0 | Frontend tooling |
| npm | 11.12.1 | Frontend package manager |
| Ollama | client 0.30.10 | Local LLM runtime |
| PostgreSQL | 14.23 Homebrew | App persistence |
| Redis | 8.8.0 | Sessions, rate limits, cache |

Key Python package versions currently installed:

| Package | Version |
| --- | --- |
| fastapi | 0.138.0 |
| uvicorn | 0.49.0 |
| google-adk | 2.3.0 |
| mcp | 1.28.0 |
| pymilvus | 2.6.15 |
| milvus-lite | 2.5.1 |
| sentence-transformers | 5.6.0 |
| codecarbon | 3.2.8 |
| llmlingua | 0.2.2, installed but disabled by default |
| asyncpg | 0.31.0 |
| redis Python client | 8.0.0 |
| httpx | 0.28.1 |

Key frontend package versions currently installed:

| Package | Version |
| --- | --- |
| React | 19.2.7 |
| React DOM | 19.2.7 |
| Vite | 6.4.3 |
| TypeScript | 5.8.3 |
| Tailwind CSS | 4.3.1 |
| lucide-react | 0.546.0 |

## Installation

Install system services on macOS with Homebrew:

```bash
brew install postgresql@14 redis ollama
brew services start postgresql@14
brew services start redis
ollama serve
```

Install required local models:

```bash
ollama pull gemma2:2b
ollama pull llama3.2:3b
```

Install backend and frontend dependencies:

```bash
cd backend
python3 -m venv anayaa
anayaa/bin/python -m pip install -r requirements.txt

cd ../frontend
npm install
```

## Setup

Create backend environment:

```bash
cd backend
cp .env.example .env
cd ..
```

Important local settings:

```text
MILVUS_ENABLED=true
ANAYAA_MILVUS_URI=data/milvus.db
OFFLINE_MODE=true
CROSS_ENCODER_ENABLED=false
LLMLINGUA_ENABLED=false
GEMINI_API_KEY=
ADK_ENABLED=true
REACT_LOOP_ENABLED=true
REACT_MAX_TURNS=2
```

Set up PostgreSQL schema:

```bash
./scripts/setup_postgres.sh
```

Run the one-time online setup while Wi-Fi is available:

```bash
./scripts/setup-online.sh
```

This intentionally downloads and caches Python packages, npm packages, Ollama models, and the configured Hugging Face embedding model, exports the embedding model to ONNX, then seeds scripture data into PostgreSQL and Milvus Lite. After this step, runtime should work without Wi-Fi with `OFFLINE_MODE=true`.

The convenience backend script can also create `.env`, generate a local JWT secret, install backend dependencies, check Ollama models, check PostgreSQL and Redis, and seed Milvus when empty:

```bash
./scripts/start-backend.sh
```

## Execution

Start backend:

```bash
./scripts/start-backend.sh
```

Start frontend in another terminal:

```bash
./scripts/start-frontend.sh
```

Open:

```text
http://localhost:5173
```

## Example To Test

Login with an email address in the UI, then ask:

```text
Is dropshipping a scam, and how should I think about it ethically if I need money?
```

Expected behavior:

- The request is accepted by the firewall.
- Planner uses local `gemma2:2b`.
- Retrieval goes through MCP and Milvus.
- Reranking uses keyword overlap because `CROSS_ENCODER_ENABLED=false`.
- Synthesis uses local `llama3.2:3b`.
- Judge uses local `llama3.2:3b`.
- Final response includes at least two citations, `Scripture grounding`, and optional `Why this guidance?`.
- Unsafe or ungrounded outputs return guarded failure statuses instead of a final answer.

Useful verification commands:

```bash
cd backend
anayaa/bin/python -m pytest tests
anayaa/bin/python -m compileall app tests

cd ../frontend
npm run build
```

Golden-metric evaluation can be run against saved prediction JSONL:

```bash
cd backend
anayaa/bin/python scripts/evaluate_golden_metrics.py /path/to/predictions.jsonl --k 3
```

Each prediction row should include:

```json
{
  "id": "eval_dropshipping_scam",
  "result": {"status": "completed", "moralPathway": "...", "auditScores": {"passed": true}},
  "retrievalCandidates": [{"verse": {"translation": "...", "keywords": ["integrity"]}}]
}
```

The report includes retrieval `precision@k`, retrieval `recall@k`, and targeted F1 for status, firewall blocking, disallowed response patterns, judge pass, and grounding-contract pass.

Lightweight load testing uses the dependency-free Python runner:

```bash
./scripts/start-backend.sh
USERS=3 DURATION_SECONDS=60 ./scripts/run-load-test.sh
```

For a public-beta check:

```bash
USERS=10 DURATION_SECONDS=300 P95_MS=90000 ./scripts/run-load-test.sh
```

The load test logs in each virtual user, calls `/api/query`, and enforces a query p95 threshold. Use `PRE_SYNTHESIS=true` to exercise the interactive HITL path; leave it `false` to exercise full synthesis. An optional k6 scenario also lives at `scripts/load-test-k6.js` for external reporting.

Request plan traces are stored in PostgreSQL:

```sql
SELECT
  created_at,
  request_id,
  detail->>'status' AS status,
  detail->'executionPlan' AS execution_plan,
  detail->'loopDetails' AS loop_details,
  detail->'agentLatencyMetrics' AS latency
FROM agent_traces
WHERE stage = 'request_plan'
ORDER BY created_at DESC
LIMIT 5;
```

## Cleanup

Light cleanup:

```bash
./scripts/free-resources.sh
```

Stop shared local services too:

```bash
./scripts/free-resources.sh --services
```

Wipe app storage:

```bash
./scripts/free-resources.sh --storage
```

Remove dependency folders as well:

```bash
./scripts/free-resources.sh --all --yes
```

After `--storage`, reseed data before querying again:

```bash
./scripts/start-backend.sh
```

## Important Side Effects

- `scripts/start-backend.sh` may create or modify `backend/.env`.
- `scripts/start-backend.sh` auto-generates a local `JWT_SECRET` if the placeholder is unsafe.
- `scripts/setup-online.sh` is the intentional Wi-Fi step. It can download Python dependencies, npm dependencies, Ollama models, Hugging Face embedding model files, and export the local embedding runtime to ONNX.
- Runtime is intended to work without Wi-Fi after setup. `OFFLINE_MODE=true` and `EMBEDDING_BACKEND=onnx` force embeddings to load from generated local ONNX assets and fail clearly if setup did not create them yet.
- `backend/scripts/seed_milvus.py` writes scripture rows to PostgreSQL and embeddings to `backend/data/milvus.db`.
- Redis stores sessions, rate limits, and semantic cache entries.
- PostgreSQL stores turns, audit logs, HITL checkpoints, feedback, eco metrics, and scripture seed state.
- PostgreSQL request plan traces in `agent_traces` are retained for `AGENT_TRACES_RETENTION_DAYS` days.
- `scripts/free-resources.sh --storage` flushes Redis DB, truncates Anayaa PostgreSQL app tables, and removes Milvus Lite DB files.
- Frontend build writes `frontend/dist`.

## Key Assumptions

- The app is run locally on macOS/Apple Silicon for development.
- Ollama is available at `http://127.0.0.1:11434`.
- Required local models are `gemma2:2b` and `llama3.2:3b`.
- `GEMINI_API_KEY` is blank for local-first execution.
- PostgreSQL and Redis are local services.
- Milvus uses local Milvus Lite at `backend/data/milvus.db`.
- Retrieval must go through MCP; the FastAPI request path should not directly open the Milvus store.
- Cross-encoder reranking and LLMLingua are disabled for local latency.
- Cache is allowed only for successful, grounded, judge-passed answers with matching cache/prompt/planner/retrieval/model versions.
- Ancient source texts may be public domain, but translations and scripture datasets may still need source/license review before public release.
- Local defaults such as localhost CORS, reload mode, and local JWT handling are development defaults, not final production deployment settings.
