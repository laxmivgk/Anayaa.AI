# Anayaa.AI

Anayaa.AI is a local-first moral guidance app. It accepts a user's dilemma, sanitizes and rewrites the query when needed, retrieves grounded scripture evidence through an MCP Milvus boundary, generates a concise local-LLM summary, audits the result for grounding and safety, and tracks per-request eco metrics.

The project is built with:

- **Backend:** FastAPI, Google ADK workflow orchestration, PostgreSQL, Redis, Milvus Lite, MCP, Ollama
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, lucide-react
- **Retrieval:** MCP stdio server wrapping Milvus hybrid search, graph expansion, and reranking
- **Safety:** sanitizer, regex firewall, PII scrubber, MCP tool allowlist, query relevance audit, guarded no-context responses

The app is intended for local development without Docker. PostgreSQL, Redis, Milvus Lite, and Ollama are required runtime services.

---

## Current Experience

The frontend has three tabs:

| Tab | Purpose |
| --- | --- |
| Active Pathway | Submit a moral dilemma and view the generated Summary, scripture evidence, and current request state |
| Scripture Center | Browse the loaded scripture corpus |
| Eco Audit | View daily energy, CO2, and request metrics |

In **Active Pathway**:

1. The user enters a dilemma.
2. `Submit` is disabled until text is entered.
3. After submission, `Submit` stays disabled until the user edits the textarea or clicks **Ask another question**.
4. The frontend sends the latest previous conversation as optional context.
5. The backend uses that context only for follow-up questions, such as "what should I do then?"
6. The Summary card shows a plain-language answer with simple sections:
   - One-line summary
   - Reflection
   - Judgment
   - Next step
   - Scripture grounding
7. Only one previous conversation is displayed, and the current answer is filtered out of that history panel.

---

## Architecture

```text
React + Vite frontend
    |
    |  POST /api/query
    v
FastAPI backend
    |
    |-- JWT auth, Redis session/rate-limit checks
    |-- sanitizer -> regex firewall -> PII scrubber
    |-- deterministic query rewriter
    |-- optional previous-conversation context for follow-ups
    |-- Google ADK workflow
    |-- MCP retrieval client
    |      |
    |      v
    |   MCP stdio server
    |      |-- milvus_hybrid_search
    |      |-- graph_expand
    |      |-- rerank_candidates_tool
    |      v
    |   Milvus Lite / scripture_verses
    |
    |-- Ollama synthesis (required local LLM runtime)
    |-- local G-Eval style judge
    |-- PostgreSQL required persistence: audit, feedback, turns, eco metrics
    |-- Redis required sessions, rate limits, and semantic cache
```

Important retrieval detail: the backend workflow calls `retrieve_via_mcp()`, and that function now runs retrieval through the MCP server boundary. The FastAPI/ADK side does **not** open `MilvusStore` directly for request retrieval. The MCP client allowlists only:

- `milvus_hybrid_search`
- `graph_expand`
- `rerank_candidates_tool`

This keeps database access behind the retrieval tool boundary and makes it easier to swap retrieval/model implementations later.

---

## Agent Pipeline

| Step | Component | What It Does |
| --- | --- | --- |
| 0 | Query Rewriter | Normalizes malformed questions and adds a moral question frame for fragments |
| 1 | Optimizer | Runs optional LLMLingua compression and builds sub-queries |
| 2 | Planner | Extracts keywords and applies lightweight feedback-aware tone |
| 3 | ReAct Reasoner | Builds the retrieval attempt and handles one bounded retry when needed |
| 4 | MCP Retriever | Calls MCP tools for Milvus search, graph expansion, and reranking |
| 5 | Synthesizer | Uses Ollama to generate the Summary from retrieved citations |
| 6 | Judge | Scores faithfulness, citation grounding, query relevance, dharma alignment, harmlessness, and privacy |
| 7 | Finalizer | Returns completed output or a guarded failure response |

### Query Rewriting

The query rewriter is deterministic and runs before retrieval. It handles common malformed inputs such as:

```text
frnd lied me forgive?
```

It can rewrite that to:

```text
friend lied me forgive?
```

For fragment-style moral inputs:

```text
friend lied me forgive
```

it adds a simple frame:

```text
friend lied me forgive. What is the wisest and kindest thing to do?
```

The response includes:

- `originalQuery`
- `rewrittenQuery`
- `queryRewriteApplied`
- `queryRewriteRules`

### Previous Conversation Context

The frontend sends the most recent previous conversation as `previousContext`. The backend sanitizes it and uses it only when the new query looks like a follow-up.

Example:

```text
Previous question: My friend lied to me. Should I forgive them?
New question: what should I do then?
```

The backend rewrites the working query into a contextual follow-up. Standalone new questions ignore previous context.

The response includes:

- `previousContextUsed`
- `previousContextQuestion`

### Multi-Query And ReAct

The app uses both without making every request expensive:

- Single clear questions use one retrieval query.
- Compound questions are split into up to three sub-queries.
- Multi-query retrieval is used only on the first pass.
- ReAct is limited to one retry (`REACT_MAX_TURNS=2`) and only runs after weak retrieval or audit failure.
- Query-relevance failures retry close to the original query instead of broadening into generic moral terms.

### Hallucination Guarding

Anayaa does not rely only on prompt wording. It also has deterministic gates:

- Non-moral/out-of-scope queries are blocked before retrieval.
- Retrieved citations must overlap with the query before synthesis runs.
- Generated summaries are checked for query relevance.
- The judge includes `query_relevance` and `citation_grounding`.
- Stale semantic-cache versions are bumped when behavior changes.

If a query is outside scope or retrieval is unrelated, the API returns a guarded failure instead of a Summary.

---

## Repository Structure

```text
backend/
  app/
    agents/          ADK workflow, query rewrite, planner, pipeline messages
    api/             FastAPI routes and auth dependencies
    auth/            JWT/session helpers
    eco/             per-request and daily eco metrics
    hitl/            HITL checkpoint support
    llm/             Ollama synthesis and prompt compression
    mcp/             MCP retrieval client and Milvus MCP server
    memory/          PostgreSQL, Redis, Milvus store, transaction stream
    observability/   audit logger and local G-Eval style judge
    privacy/         retention cleanup
    retrieval/       corpus loading, embeddings, hybrid search/rerank logic
    security/        sanitizer, firewall, PII scrubber
    main.py          FastAPI app and startup dependency checks
  data/
    scriptures.json  local scripture corpus
    milvus.db        default Milvus Lite database file
  scripts/
    seed_milvus.py   seeds PostgreSQL/Milvus scripture data
  requirements.txt

frontend/
  src/
    App.tsx          main UI, auth flow, query form, Summary/history rendering
    main.tsx
    index.css
  package.json
  vite.config.ts

infra/
  init.sql           PostgreSQL schema
  ports.env          local port reference

scripts/
  clean-local.sh
  free-resources.sh

  setup_postgres.sh
  start-backend.sh
  start-frontend.sh
```

Note: some local virtual environment and build-output folders may exist during development; they are not part of the source architecture.

---

## Local Setup

### Prerequisites

| Tool | Purpose |
| --- | --- |
| Python 3.10+ | Backend runtime |
| Node.js 18+ | Frontend runtime |
| PostgreSQL 14+ | turns, feedback, audit logs, eco metrics, HITL checkpoints |
| Redis 6+ | sessions, rate limiting, semantic cache |
| Milvus Lite | embedded vector database |
| Ollama | local LLM runtime |



## Data And Persistence

| Store | Data |
| --- | --- |
| PostgreSQL | turns, feedback records, audit logs, HITL checkpoints, eco metrics |
| Redis | sessions, rate limits, semantic cache |
| Milvus Lite | scripture vector index in `backend/data/milvus.db` |
| Browser localStorage | JWT/email and last two local UI conversation entries |

The scripture corpus loads from:

```text
backend/data/scriptures.json
```

Seed or reseed Milvus:

```bash
cd backend
source .venv/bin/activate
python scripts/seed_milvus.py
```

### Startup Scripts

From the repo root:

```bash
./scripts/setup_postgres.sh
./scripts/start-backend.sh
```

In a second terminal:

```bash
./scripts/start-frontend.sh
```

Open in the browser:

```text
http://localhost:5173
```

Log in with any valid email address. The local auth route issues a JWT.

| Script | Purpose |
| --- | --- |
| `scripts/setup_postgres.sh` | Initializes the local PostgreSQL user, database, and schema from `infra/init.sql` |
| `scripts/start-backend.sh` | Creates/uses `backend/.venv`, installs dependencies, prepares `.env`, checks services, seeds Milvus if needed, and starts FastAPI on port `8000` |
| `scripts/start-frontend.sh` | Installs frontend dependencies if needed and starts Vite on port `5173` |
| `scripts/clean-local.sh` | Removes generated caches/build output, with optional dependency/data cleanup flags |
| `scripts/free-resources.sh` | Stops Anayaa app processes and cleans generated files; optional flags stop services, wipe app storage, and remove dependencies |

`start-backend.sh` does the following:

- creates `backend/.venv` if missing,
- installs Python dependencies,
- creates `backend/.env` from `.env.example` if missing,
- generates a unique `JWT_SECRET` in `backend/.env` when the placeholder or old demo value is present,
- removes legacy `MILVUS_URI` entries,
- checks PostgreSQL, Redis, Ollama, and Milvus,
- seeds Milvus when the collection is empty,
- starts FastAPI on `http://localhost:8000`.

### Manual Startup

Use this only when you do not want the helper scripts.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/seed_milvus.py
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```



## Environment Configuration

Backend settings load from `backend/.env` through Pydantic Settings.

### Required Services

| Variable | Default | Description |
| --- | --- | --- |
| `POSTGRES_ENABLED` | `true` | PostgreSQL is required |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `MILVUS_ENABLED` | `true` | Milvus retrieval is required |
| `ANAYAA_MILVUS_URI` | `data/milvus.db` | Milvus Lite path or standalone URI |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama runtime URL |

Use `ANAYAA_MILVUS_URI`, not `MILVUS_URI`. `MILVUS_URI` conflicts with pymilvus global configuration.

### Workflow And Safety

| Variable | Default | Description |
| --- | --- | --- |
| `ADK_ENABLED` | `true` | Enables Google ADK workflow |
| `REACT_LOOP_ENABLED` | `true` | Enables bounded retry loop |
| `REACT_MAX_TURNS` | `2` | Initial pass plus one retry |
| `RETRIEVAL_CONFIDENCE_THRESHOLD` | `40.0` | Minimum retrieval score for synthesis |
| `AUDIT_MIN_SCORE` | `3` | Minimum judge score per dimension |
| `HITL_ENABLED` | `true` | HITL support exists, but `/api/query` currently requests direct completion |
| `RATE_LIMIT_PER_MINUTE` | `20` | Per-session request limit |

### LLM And Retrieval Models

| Variable | Default | Description |
| --- | --- | --- |
| `EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Embedding model used for scripture vectors |
| `CROSS_ENCODER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Optional reranker model |
| `CROSS_ENCODER_ENABLED` | `false` | Disabled by default for local latency |
| `LLMLINGUA_ENABLED` | `false` in `.env.example` | Optional prompt compression |
| `LLMLINGUA_MODEL` | `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank` | Compression model |
| `GEMINI_API_KEY` | empty | Reserved for optional cloud routing; local synthesis currently uses Ollama |

### Minimal Local `.env`

```env
JWT_SECRET=change-me-generate-with-start-backend
POSTGRES_ENABLED=true
MILVUS_ENABLED=true
ANAYAA_MILVUS_URI=data/milvus.db
REDIS_URL=redis://localhost:6379/0
OLLAMA_BASE_URL=http://localhost:11434
LLMLINGUA_ENABLED=false
ADK_ENABLED=true
REACT_LOOP_ENABLED=true
REACT_MAX_TURNS=2
```


.env.example:
JWT_SECRET=change-me-generate-with-start-backend

# Required services
POSTGRES_ENABLED=true
REDIS_URL=

# Required retrieval service
MILVUS_ENABLED=true

# PostgreSQL (required; install locally, run infra/init.sql)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=anayaa
POSTGRES_USER=anayaa
POSTGRES_PASSWORD=<set-in-secret-manager>.

# Milvus — embedded Milvus Lite (no server) or standalone http://localhost:19530
# Use ANAYAA_MILVUS_URI (not MILVUS_URI — that name conflicts with pymilvus global config)
ANAYAA_MILVUS_URI=data/milvus.db
MILVUS_COLLECTION=scripture_verses
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
CROSS_ENCODER_ENABLED=false

# LLM provider
OLLAMA_BASE_URL=http://localhost:11434

# Optional cloud LLM routing
GEMINI_API_KEY=

HITL_ENABLED=true
RATE_LIMIT_PER_MINUTE=10

# LLMLingua prompt compression (downloads model on first use)
LLMLINGUA_ENABLED=false
LLMLINGUA_MODEL=microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank
LLMLINGUA_USE_V2=true
LLMLINGUA_USE_LONGLLMLINGUA=false
LLMLINGUA_DEVICE=auto
LLMLINGUA_COMPRESSION_RATE=0.5

# Google ADK workflow orchestration (MCP Milvus retrieval + LLM synthesis)
ADK_ENABLED=true
RETRIEVAL_CONFIDENCE_THRESHOLD=40
AUDIT_MIN_SCORE=3
REACT_LOOP_ENABLED=true
REACT_MAX_TURNS=2

---

## API

Base URL:

```text
http://localhost:8000
```

Interactive docs:

```text
http://localhost:8000/docs
```

### Authentication

```http
POST /api/auth/login
Content-Type: application/json

{ "email": "user@example.com" }
```

Use the returned token:

```http
Authorization: Bearer <token>
```

JWT sessions default to 15 minutes. The frontend shows a warning modal before expiry with **Continue** and **Cancel**.

### Query

```http
POST /api/query
Authorization: Bearer <token>
Content-Type: application/json

{
  "query": "My friend lied to me. Should I forgive them?",
  "previousContext": {
    "question": "Optional previous question",
    "response": "Optional previous response"
  }
}
```

`previousContext` is optional. It is sanitized and only used for follow-up-style queries.

### Query Response Fields

| Field | Description |
| --- | --- |
| `status` | `completed`, `insufficient_context`, `retrieval_unavailable`, `quality_threshold_not_met`, etc. |
| `moralPathway` | Generated Summary when completed |
| `originalQuery` | User-submitted query after security preprocessing |
| `rewrittenQuery` | Query used by planner/retrieval/synthesis |
| `queryRewriteApplied` | Whether deterministic rewriting changed the query |
| `queryRewriteRules` | Rewrite rules that fired |
| `previousContextUsed` | Whether previous conversation context influenced intent |
| `previousContextQuestion` | Previous question used for follow-up context |
| `retrievalQueries` | Actual retrieval queries used |
| `multiQueryUsed` | Whether compound-query retrieval was used |
| `citations` | Scripture verses used for synthesis |
| `rerankedCitations` | Reranked retrieval candidates |
| `retrievalViaMcp` | Whether retrieval went through MCP |
| `auditScores` | Local judge scores, pass/fail, failed dimensions, grounding terms |
| `powerMetrics` | Per-request energy and CO2 metrics |
| `ecoBreakdown` | Stage-by-stage energy and CO2 metrics |
| `cacheHit` | Whether Redis semantic cache served the response |
| `userMessage` | User-facing message for guarded failures |

### Other Endpoints

| Method | Endpoint | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/auth/login` | No | Issue JWT |
| `POST` | `/api/query` | Yes | Run the guidance pipeline |
| `POST` | `/api/hitl/resume` | Yes | Resume a HITL checkpoint |
| `POST` | `/api/feedback` | Yes | Store feedback for a request |
| `DELETE` | `/api/feedback` | Yes | Delete current user's feedback |
| `DELETE` | `/api/feedback/{request_id}` | Yes | Delete one feedback record |
| `GET` | `/api/eco/daily` | Yes | Daily eco totals |
| `GET` | `/api/system/status` | No | Runtime and corpus status |
| `GET` | `/api/system/scriptures` | No | Loaded scripture corpus |
| `GET` | `/api/system/streams` | No | In-process transaction stream |
| `GET` | `/api/health` | No | Health check |
| `GET` | `/api/health/deep` | No | Deep health check |


---

### Cleaning Local Files

Default cleanup removes generated caches and build output only:

```bash
./scripts/clean-local.sh
```

Remove dependency folders too:

```bash
./scripts/clean-local.sh --deps
```

Remove local Milvus data and startup logs too:

```bash
./scripts/clean-local.sh --data
```

Use non-interactive data cleanup only when you are sure:

```bash
./scripts/clean-local.sh --data --yes
```

Data cleanup removes `backend/data/milvus.db`, so run the backend startup script or `cd backend && python scripts/seed_milvus.py` afterward to reseed retrieval.

### Freeing All Resources

Use this when you want one command for stopping the local app and freeing resources.

Default mode stops Anayaa app processes on local ports, stops orphaned backend/frontend/MCP child processes, and removes generated caches/build output:

```bash
./scripts/free-resources.sh
```

Also stop shared local services on their configured ports:

```bash
./scripts/free-resources.sh --services
```

This can stop PostgreSQL, Redis, Ollama, and standalone Milvus if they are listening on the local project ports.

Also wipe app storage:

```bash
./scripts/free-resources.sh --storage
```

Storage cleanup flushes the configured Redis DB, truncates Anayaa PostgreSQL app tables, resets `corpus_status`, and removes the local Milvus Lite DB file. After storage cleanup, run `./scripts/start-backend.sh` or `cd backend && python scripts/seed_milvus.py` to reseed retrieval.

Full cleanup in one non-interactive command:

```bash
./scripts/free-resources.sh --all --yes
```

`--all` enables `--services`, `--storage`, and `--deps`. Use it only when you want to stop services, wipe app data, and remove `backend/.venv` plus `frontend/node_modules`.

### Verification Commands

```bash
cd backend
.venv/bin/python -m compileall app
```

```bash
cd frontend
npm run build
```

---
```

---

## Development Notes

- FastAPI docs are at `http://localhost:8000/docs`.
- CORS allows `http://localhost:5173` and `http://127.0.0.1:5173`.
- MCP retrieval code lives in `backend/app/mcp/`.
- `backend/app/mcp/client.py` is the app-side MCP client.
- `backend/app/mcp/milvus_retrieval_server.py` is the DB-owning MCP server.
- The current hot path should report `retrievalViaMcp: true` for real retrieval attempts.
- Out-of-scope prompts should return guarded failures, not summaries.
- After backend changes, restart FastAPI; the dev server will not always reload long-lived ADK/MCP state cleanly.
