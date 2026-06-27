# Anayaa.AI

<<<<<<< HEAD
Anayaa.AI is a local-first scripture-grounded guidance app for moral and life dilemmas. It accepts a user's question, sanitizes and rewrites the query when needed, retrieves scripture evidence through an MCP and Milvus boundary, generates guidance with local LLMs, audits the result for faithfulness and safety, and tracks request-level eco metrics.

The project is built for local development without Docker.

- Backend: FastAPI, PostgreSQL, Redis, Milvus Lite, MCP, Google ADK, Ollama
- Frontend: React 19, TypeScript, Vite 6, Tailwind CSS, lucide-react
- Retrieval: scripture JSON corpus, sentence-transformer embeddings, Milvus hybrid search, graph expansion, reranking
- Safety: sanitizer, regex firewall, PII scrubber, MCP tool allowlist, G-Eval style audit, deterministic grounding checks
- Auth: PostgreSQL-backed users, salted PBKDF2 password hashes, JWT sessions, local reset-code flow
- Local models: `gemma2:2b` for lightweight classification, `qwen3:4b` for planning/retry planning/judging, and `llama3.2:3b` for final guidance synthesis

## Current Experience

The frontend has three main tabs.

| Tab | Purpose |
| --- | --- |
| Active Pathway | Enter a dilemma and choose interactive or direct guidance |
| Scripture Center | Browse the local scripture corpus |
| Eco Audit | View daily energy, CO2, request metrics, and G-Eval audit status |

In Active Pathway:

1. The user logs in with an email address and password. A new email self-registers on first login, while existing emails must use their saved password.
2. The user enters a dilemma in the query box.
3. The user can choose `The Interactive Guidance` or `The Guidance`.
4. `The Interactive Guidance` pauses before synthesis so the user can adjust concepts, select scripture candidates, or add a manual scripture. Clicking `Compile guidance` locks the interactive controls while the final guidance is generated.
5. `The Guidance` runs the same pipeline directly without the pre-synthesis review pause.
6. The query box shows a 4000-character limit. After an answer loads, the query box becomes read-only. The `Next dilemna` button starts the next query.
7. The login page includes `Forgot password?`; local reset codes are printed to the backend terminal.
8. The UI shows only user-facing guidance. Internal guidance validation details are not shown.
9. Scripture Evidence shows only citations that were actually used in the final answer.

The visible answer is organized around:

- Summary
- Reflection
- Judgement
- Next step
- Scripture grounding
- Scripture Evidence
- Eco and audit metadata
=======
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
| Active Pathway | Enter a moral dilemma and choose interactive or direct scripture-grounded guidance |
| Scripture Center | Browse the loaded scripture corpus |
| Eco Audit | View daily energy, CO2, and request metrics |

In **Active Pathway**:

1. The user enters a dilemma.
2. `Clear`, `The Interactive Guidance`, and `The Guidance` are shown under the query box.
3. `The Interactive Guidance` starts pre-synthesis verification. The app pauses after planning and retrieval so the user can review concepts, deselect scripture candidates, or manually inject a scripture from the local corpus before clicking **Compile guidance**.
4. `The Guidance` runs the same moral-guidance pipeline directly without the interactive review pause.
5. Loading text is action-specific: only the clicked top-level guidance button shows `Processing...`, and only **Compile guidance** shows `Compiling...` during synthesis.
6. Each query is treated as a single-turn request. The app does not send previous conversation context while multi-turn support is disabled.
7. The Previous Conversation card can still show local UI history for reference only; it is not sent to the backend or used for retrieval.
8. The Summary card shows a plain-language answer with the opening summary consolidated into one block, followed by simple sections:
   - One-line summary
   - Reflection
   - Judgment
   - Next step
   - Scripture grounding

---
>>>>>>> origin/main

## Architecture

```text
React + Vite frontend
    |
<<<<<<< HEAD
    |  JWT-authenticated API calls
    v
FastAPI backend
    |
    |-- PostgreSQL users, JWT auth, Redis sessions, rate limits
    |-- sanitizer -> regex firewall -> PII scrubber
    |-- deterministic query rewrite
    |-- LLM planner and bounded ReAct retrieval loop
    |-- MCP retrieval client
    |      |
    |      v
    |   MCP stdio retrieval server
=======
    |  POST /api/query
    v
FastAPI backend
    |
    |-- JWT auth, Redis session/rate-limit checks, authenticated token refresh
    |-- sanitizer -> regex firewall -> PII scrubber
    |-- deterministic query rewriter
    |-- optional previous-conversation context for follow-ups
    |-- Google ADK workflow
    |-- MCP retrieval client
    |      |
    |      v
    |   MCP stdio server
>>>>>>> origin/main
    |      |-- milvus_hybrid_search
    |      |-- graph_expand
    |      |-- rerank_candidates_tool
    |      v
<<<<<<< HEAD
    |   Milvus Lite scripture_verses collection
    |
    |-- optional pre-synthesis human review
    |-- Ollama synthesis with section-contract cleanup
    |-- LLM judge and deterministic grounding contract
    |-- PostgreSQL persistence
    |-- Redis semantic cache and session state
```

Runtime retrieval goes through the MCP tool boundary. The FastAPI request path does not open `MilvusStore` directly for retrieval. The MCP client allowlists only:
=======
    |   Milvus Lite / scripture_verses
    |
    |-- Ollama synthesis (required local LLM runtime)
    |-- local G-Eval style judge
    |-- PostgreSQL required persistence: audit, feedback, turns, HITL checkpoints, eco metrics
    |-- Redis required sessions, query/refresh rate limits, and semantic cache
```

Important retrieval detail: the backend workflow calls `retrieve_via_mcp()`, and that function now runs retrieval through the MCP server boundary. The FastAPI/ADK side does **not** open `MilvusStore` directly for request retrieval. The MCP client allowlists only:
>>>>>>> origin/main

- `milvus_hybrid_search`
- `graph_expand`
- `rerank_candidates_tool`

<<<<<<< HEAD
This keeps scripture retrieval behind a clear tool boundary and makes retrieval behavior easier to audit.

## Guidance Pipeline

| Step | Component | What it does |
| --- | --- | --- |
| 0 | Query Rewriter | Normalizes malformed wording and frames fragments as moral questions |
| 1 | Optimizer | Builds semantic cache keys and optional compressed prompts |
| 2 | Planner | Extracts dilemma-specific concepts and tone hints with the selected LLM planner |
| 3 | ReAct Reasoner | Runs bounded retrieval attempts when the first pass is weak; retry planning is LLM-driven and has no deterministic fallback |
| 4 | MCP Retriever | Searches, graph-expands, and reranks scripture candidates |
| 5 | Pre-Synthesis Review | Optional interactive pause before final synthesis |
| 6 | Synthesizer | Generates the guidance from retrieved or selected citations and normalizes section labels into the UI contract |
| 7 | Audit | Scores faithfulness, citation grounding, relevance, dharma alignment, harmlessness, and privacy |
| 8 | Finalizer | Returns guidance, an approval checkpoint, or a user-facing quality message |

For interactive compile, the judge evaluates the final answer against the rewritten dilemma plus the selected concepts. This matches the direct guidance path more closely than judging only against the concept list.

Each API query is currently single-turn. The backend does not pass previous conversation context into retrieval or synthesis while multi-turn support is disabled.

Planner and synthesizer failures are surfaced as explicit workflow statuses instead of silently falling back to deterministic answers. This keeps testing honest when a local model is unavailable, returns invalid JSON, or produces a draft that fails the guidance contract.

## G-Eval Audit

The G-Eval audit icon represents the automated quality gate for the generated guidance. A response must satisfy the configured minimum score across audit dimensions and pass the grounding contract before it is treated as complete guidance.

The UI keeps this user-facing:

- It can show whether the audit passed or needs review.
- It can show LLM score checks in the audit area.
- It does not show the internal Guidance validation block.

## Repository Layout

```text
.
|-- backend/
|   |-- app/
|   |   |-- agents/          # workflow, ADK orchestration, cache policy, pipeline messages
|   |   |-- api/routes/      # auth, query, system, HITL resume, feedback, eco
|   |   |-- auth/            # identity, JWT, password hashing, users, sessions
|   |   |-- eco/             # request and daily eco metrics
|   |   |-- hitl/            # pre-synthesis checkpoints
|   |   |-- llm/             # local model routing, generation, prompt compression
|   |   |-- mcp/             # retrieval MCP client and server
|   |   |-- memory/          # PostgreSQL, Redis, Milvus helpers
|   |   |-- observability/   # audit logger, G-Eval judge, grounding contract
|   |   |-- retrieval/       # corpus, embeddings, hybrid search
|   |   |-- security/        # sanitizer, firewall, privacy scrubber
|   |   `-- main.py
|   |-- data/                # local scripture and Milvus Lite data
|   |-- scripts/             # backend utility scripts, user creation, retrieval seeding
|   `-- tests/
|-- frontend/
|   |-- src/
|   `-- package.json
|-- infra/
|   `-- init.sql
|-- scripts/
|   |-- setup-online.sh
|   |-- setup_postgres.sh
|   |-- start-backend.sh
|   |-- start-frontend.sh
|   |-- run-load-test.sh
|   |-- pre-merge-checks.sh
|   `-- free-resources.sh
`-- README.md
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL running locally
- Redis running locally
- Ollama installed locally
- Enough disk space for local Python packages, embedding assets, Milvus Lite data, and Ollama models

The startup scripts expect PostgreSQL at `127.0.0.1:5432`, Redis at `redis://127.0.0.1:6379/0`, and Ollama at `http://127.0.0.1:11434` unless overridden in `backend/.env`.

## Local Setup

Run the one-time online setup first. Keep internet access on for this step because it installs dependencies, pulls local models, caches embedding assets, and seeds retrieval.

```bash
./scripts/setup_postgres.sh
./scripts/setup-online.sh
```

Then start the app:

```bash
./scripts/start-backend.sh
./scripts/start-frontend.sh
```

Open:

- Frontend: `http://127.0.0.1:5173`
- Backend docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/api/health`
- Deep health: `http://localhost:8000/api/health/deep`

`scripts/start-backend.sh` creates `backend/.env` from `backend/.env.example` when needed, generates a safe local `JWT_SECRET`, checks PostgreSQL and Redis, ensures Ollama models are available, verifies Milvus Lite, seeds empty retrieval data, runs lightweight schema migrations such as user reset columns, and starts FastAPI on port 8000.

The startup scripts expect these local Ollama models:

- `gemma2:2b`
- `qwen3:4b`
- `llama3.2:3b`

Current local model routing:

| Task | Model |
| --- | --- |
| Lightweight classification | `gemma2:2b` |
| Planner | `qwen3:4b` |
| ReAct retry planner | `qwen3:4b` |
| Synthesizer | `llama3.2:3b` |
| G-Eval judge | `qwen3:4b` |

When `GEMINI_API_KEY` is configured, planner and synthesizer routing can use the optional cloud path. Local-first development assumes the Ollama models above.

## Environment

The main local settings live in `backend/.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `JWT_SECRET` | generated locally | Required JWT signing secret, at least 32 characters |
| `JWT_EXP_MINUTES` | `15` | Access token lifetime |
| `POSTGRES_ENABLED` | `true` | PostgreSQL is required |
| `POSTGRES_HOST` | `127.0.0.1` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `anayaa` | PostgreSQL database |
| `POSTGRES_USER` | `anayaa` | PostgreSQL user |
| `POSTGRES_PASSWORD` | `anayaa_dev` | Local development password |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Sessions, rate limits, cache |
| `MILVUS_ENABLED` | `true` | Milvus retrieval is required |
| `ANAYAA_MILVUS_URI` | `data/milvus.db` | Milvus Lite path or standalone Milvus URI |
| `MILVUS_COLLECTION` | `scripture_verses` | Vector collection name |
| `OFFLINE_MODE` | `true` | Uses cached local assets after setup |
| `EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Embedding model |
| `CROSS_ENCODER_ENABLED` | `false` | Optional reranker toggle |
| `CROSS_ENCODER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder model |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama endpoint |
| `GEMINI_API_KEY` | empty | Optional cloud routing for planner/synthesizer |
| `HITL_ENABLED` | `true` | Enables interactive pre-synthesis checkpoints |
| `RATE_LIMIT_PER_MINUTE` | `20` | Query rate limit |
| `SESSION_REFRESH_RATE_LIMIT_PER_MINUTE` | `10` | Token refresh rate limit |
| `LLMLINGUA_ENABLED` | `false` | Optional prompt compression toggle |
| `LLMLINGUA_MODEL` | `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank` | Optional compression model |
| `LLMLINGUA_COMPRESSION_RATE` | `0.5` | Optional prompt compression target |
| `ADK_ENABLED` | `true` | Enables ADK workflow orchestration |
| `RETRIEVAL_CONFIDENCE_THRESHOLD` | `40` | Minimum retrieval confidence target |
| `AUDIT_MIN_SCORE` | `3` | Minimum audit score per dimension |
| `REACT_LOOP_ENABLED` | `true` | Enables bounded retrieval retry behavior |
| `REACT_MAX_TURNS` | `2` | Maximum ReAct retrieval turns |
| `AGENT_TRACES_RETENTION_DAYS` | `30` | Local retention window for stored agent traces |
| `REQUEST_ECO_METRICS_RETENTION_DAYS` | `90` | Local retention window for request eco metrics |
| `AUDIT_LOGS_RETENTION_DAYS` | `90` | Local retention window for G-Eval audit logs |
| `HITL_TERMINAL_RETENTION_DAYS` | `7` | Local retention window for completed HITL checkpoints |
| `TURNS_RETENTION_DAYS` | `30` | Local retention window for stored query turns |
| `RETENTION_CLEANUP_INTERVAL_SECONDS` | `86400` | Background cleanup cadence |

Do not use `MILVUS_URI` in `.env`. Use `ANAYAA_MILVUS_URI`; the generic `MILVUS_URI` name can conflict with `pymilvus` global configuration.

## Login Users

Login users are stored in PostgreSQL. Passwords are never stored in `.env`; the database stores salted PBKDF2 password hashes.

When a new email logs in for the first time, Anayaa creates that user with the password entered on the login screen. Later logins for that same email must use the saved password. This is local self-registration; no login credentials are stored in `.env`.

If a user forgets their password, click `Forgot password?` on the login screen and request a reset code. The backend prints the one-time code to the local backend terminal; enter that code with a new password to update the account. Reset codes expire after 15 minutes and are stored only as hashes.

You can also create or update a local login user from the terminal:

```bash
cd backend
python scripts/create_user.py --email you@example.com
```

The script prompts for the password without echoing it in the terminal.

## API Overview

Authentication:

- `POST /api/auth/login`
- `POST /api/auth/password-reset/request`
- `POST /api/auth/password-reset/confirm`
- `POST /api/auth/refresh`

Guidance:

- `POST /api/query`
- `POST /api/hitl/resume`
- `POST /api/feedback`
- `DELETE /api/feedback`
- `DELETE /api/feedback/{request_id}`

System and observability:

- `GET /api/system/status`
- `GET /api/system/scriptures`
- `GET /api/system/streams`
- `GET /api/eco/daily`
- `GET /api/health`
- `GET /api/health/deep`

Example query request:

```json
{
  "query": "How can I be disciplined?",
=======
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
| 5 | Pre-Synthesis Verification | Optional HITL pause that presents proposed concepts and candidate scriptures before synthesis |
| 6 | Synthesizer | Uses Ollama to generate the Summary from approved or directly retrieved citations |
| 7 | Judge | Scores faithfulness, citation grounding, query relevance, dharma alignment, harmlessness, and privacy |
| 8 | Finalizer | Returns completed output, an interactive approval checkpoint, or a guarded failure response |

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

### Multi-Query And ReAct

The app uses both without making every request expensive:

- Single clear questions use one retrieval query.
- Compound questions are split into up to three sub-queries.
- Multi-query retrieval is used only on the first pass.
- ReAct is limited to one retry (`REACT_MAX_TURNS=2`) and only runs after weak retrieval or audit failure.
- Query-relevance failures retry close to the original query instead of broadening into generic moral terms.

### Pre-Synthesis Verification

When the frontend sends `preSynthesisVerification: true`, the workflow can stop before synthesis and return `status: awaiting_pre_synthesis_approval`. The response includes a `hitl` payload with:

- `workflowRunId`
- `approvalTitle`
- `instructions`
- `proposedKeywords`
- `candidateScriptures`
- `selectedVerseIds`

The user can adjust concepts, select or deselect candidate scriptures, and manually inject a scripture selected from the local scripture database. The frontend then resumes the checkpoint through `POST /api/hitl/resume`.

When `preSynthesisVerification: false`, the same retrieval and synthesis workflow runs directly and returns the resolved guidance without pausing.

### Retrieval Quality Notes

The planner and reranker preserve concrete dilemma terms such as `business`, `betrayal`, `partner`, `revenge`, `company`, and `financial` so practical business-survival questions do not collapse into generic moral advice. The synthesis prompt also asks for richer scripture grounding and practical next steps when the dilemma involves business or money.

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
| `HITL_ENABLED` | `true` | Enables pre-synthesis verification when a request sets `preSynthesisVerification: true` |
| `RATE_LIMIT_PER_MINUTE` | `20` | Per-session request limit |
| `SESSION_REFRESH_RATE_LIMIT_PER_MINUTE` | `10` | Per-session refresh limit for `/api/auth/refresh` |

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
HITL_ENABLED=true
RATE_LIMIT_PER_MINUTE=20
SESSION_REFRESH_RATE_LIMIT_PER_MINUTE=10
```


### Example `.env`

```env
JWT_SECRET=change-me-generate-with-start-backend

# Required services
POSTGRES_ENABLED=true
REDIS_URL=redis://localhost:6379/0

# Required retrieval service
MILVUS_ENABLED=true

# PostgreSQL (required; install locally, run infra/init.sql)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=anayaa
POSTGRES_USER=anayaa
POSTGRES_PASSWORD=anayaa_dev

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
RATE_LIMIT_PER_MINUTE=20
SESSION_REFRESH_RATE_LIMIT_PER_MINUTE=10

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
```

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

Active sessions use a sliding refresh flow:

- `POST /api/auth/refresh` requires the current bearer token.
- The backend verifies the token and Redis session before extending the same session.
- Refresh keeps the same `session_id`, extends the Redis TTL, and returns a new JWT.
- The frontend refreshes automatically when a guidance action starts near expiry.
- The warning modal remains as a fallback, and **Continue** now calls `/api/auth/refresh`.
- Refresh attempts have a separate Redis rate limit from query requests.

```http
POST /api/auth/refresh
Authorization: Bearer <token>
```

### Query

```http
POST /api/query
Authorization: Bearer <token>
Content-Type: application/json

{
  "query": "My friend lied to me. Should I forgive them?",
>>>>>>> origin/main
  "preSynthesisVerification": true
}
```

<<<<<<< HEAD
Use `preSynthesisVerification: true` for Interactive Guidance and `false` for direct Guidance.

`POST /api/auth/login` self-registers unknown emails with the submitted password. Existing emails require the stored password. `POST /api/auth/password-reset/request` does not reveal whether an email exists; when it does, the reset code is printed to the local backend terminal.

Important response fields include:

- `status`
- `originalQuery`
- `rewrittenQuery`
- `queryRewriteApplied`
- `keywords`
- `citations`
- `moralPathway`
- `auditScores`
- `guidanceReasons`
- `hitl`
- `powerMetrics`
- `transactionLog`
- `cacheHit`

Some fields are internal or diagnostic. The frontend intentionally hides validation details that are not useful to the end user.

Common statuses:

| Status | Meaning |
| --- | --- |
| `completed` | Guidance passed retrieval, synthesis, and audit |
| `awaiting_pre_synthesis_approval` | Interactive Guidance paused before synthesis for concept/scripture review |
| `awaiting_approval` | HITL approval checkpoint exists after synthesis |
| `planner_unavailable` | The strategic planner LLM failed or returned invalid planner JSON |
| `synthesizer_unavailable` | The synthesizer failed or produced a draft rejected by the guidance contract |
| `retrieval_unavailable` | MCP/Milvus scripture retrieval failed operationally |
| `insufficient_context` | Retrieval completed but did not find relevant scripture context |
| `quality_threshold_not_met` | The generated guidance failed audit or grounding checks |

## Verification

Run the full local verification gate before merging:
=======
Multi-turn context is disabled for now. `/api/query` treats each request as standalone and does not use previous conversation context.

`preSynthesisVerification` is optional and defaults to `true`. Set it to:

- `true` for **The Interactive Guidance** flow, where the app pauses for scripture/concept review before synthesis.
- `false` for **The Guidance** flow, where the app computes the resolved pathway directly.

### Query Response Fields

| Field | Description |
| --- | --- |
| `status` | `completed`, `awaiting_pre_synthesis_approval`, `insufficient_context`, `retrieval_unavailable`, `quality_threshold_not_met`, etc. |
| `moralPathway` | Generated Summary when completed |
| `hitl` | Interactive checkpoint data when `status` is `awaiting_pre_synthesis_approval` |
| `originalQuery` | User-submitted query after security preprocessing |
| `rewrittenQuery` | Query used by planner/retrieval/synthesis |
| `queryRewriteApplied` | Whether deterministic rewriting changed the query |
| `queryRewriteRules` | Rewrite rules that fired |
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

### HITL Resume

```http
POST /api/hitl/resume
Authorization: Bearer <token>
Content-Type: application/json

{
  "workflowRunId": "<workflow-run-id>",
  "decision": "approve",
  "concepts": ["forgiveness", "justice", "financial survival"],
  "selectedVerseIds": ["verse-id-1", "verse-id-2"],
  "manualVerse": {
    "faith": "Hinduism",
    "source": "Bhagavad Gita",
    "chapter": "2",
    "verse": "63",
    "translation": "Short selected verse text",
    "context": "Why this verse matters",
    "keywords": "anger, delusion, judgment"
  }
}
```

Use `decision: approve` to compile final guidance from selected scriptures and any manual verse. Use `decision: reject` to cancel the checkpoint and return the draft pathway if one exists.

### Other Endpoints

| Method | Endpoint | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/auth/login` | No | Issue JWT |
| `POST` | `/api/auth/refresh` | Yes | Extend the active session and return a fresh JWT |
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

Run the full pre-merge suite from the repo root:
>>>>>>> origin/main

```bash
./scripts/pre-merge-checks.sh
```

<<<<<<< HEAD
That script runs:

- Python compile checks for `backend/app` and `backend/tests`
- Backend tests
- Frontend production build

Useful targeted checks while developing:

```bash
cd backend
.venv/bin/python -m pytest tests/test_llm_strategic_planner.py tests/test_llm_react_retry_planner.py tests/test_guidance_section_contract.py tests/test_grounding_contract.py tests/test_guidance_reasons.py tests/test_hitl_compile_audit_query.py
=======
The same checks run in GitHub Actions for pull requests and pushes to `main` or `master`:

- backend compile check
- backend unit tests
- frontend production build

Install backend test dependencies first if your local venv does not have `pytest`:

```bash
cd backend
.venv/bin/python -m pip install -r requirements-dev.txt
```

Individual commands:

```bash
cd backend
.venv/bin/python -m compileall app tests
.venv/bin/python -m pytest tests
>>>>>>> origin/main
```

```bash
cd frontend
npm run build
```

<<<<<<< HEAD
## Local Operations

Free common local development resources:

```bash
./scripts/free-resources.sh
```

Run load tests:

```bash
export ANAYAA_LOAD_TEST_EMAIL="codex.test@example.com"
export ANAYAA_LOAD_TEST_PASSWORD="the-password-for-the-load-test-user"
./scripts/run-load-test.sh
```

The load-test email self-registers if it does not already exist. If it already exists, the password must match or be reset first.

Clean local generated runtime data:

```bash
./scripts/clean-local.sh
```

Review a single request path quickly by logging in, sending a query to `/api/query`, and checking:

- `status`
- `moralPathway`
- `citations`
- `auditScores`
- `auditScores.groundingContract`
- `cacheHit`

## Production Notes

The repository is configured for local development. Before production deployment, harden the following:

- Store `JWT_SECRET` and database credentials in a secret manager.
- Keep login passwords out of environment variables; store only password hashes or use a production auth provider.
- Replace terminal-printed password reset codes with an email provider or managed auth flow before production use.
- Use HTTPS only.
- Replace localhost CORS with the deployed frontend origin.
- Review browser token storage and cookie/session strategy.
- Use managed or hardened PostgreSQL, Redis, and vector storage.
- Disable development reload behavior.
- Configure observability, backups, retention, and alerting.
- Treat optional cloud LLM routing as a privacy-sensitive integration.

Local defaults such as localhost CORS, generated dev secrets, and local JWT storage are development conveniences, not production security guidance.
=======
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
>>>>>>> origin/main
