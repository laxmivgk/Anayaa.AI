
# Anayaa.AI - Kaggle Capstone Submission for Agents for Good
## License & AI Safety Notice

This project's custom code, notebooks, and architecture are licensed under the [Creative Commons Attribution 4.0 International License](./LICENSE) per Kaggle Capstone requirements.

However, this project interfaces with local foundational models (Meta Llama 3.2, Google Gemma, and Alibaba Qwen) and tools which are independently governed by their respective community licenses and commercial terms. The CC-BY 4.0 license applies strictly to the logic, frontend, and pipeline configurations authored in this repository.

# Anayaa.AI
 Anayaa.AI is a local-first, eco-friendly scripture-grounded guidance app for moral and life dilemmas. By implementing edge-optimization parameters Anayaa slashes single-query energy costs to a fraction of a watt-hour (~0.06g CO₂e).

## Problem
Anayaa.AI solves the problem of getting thoughtful, grounded guidance for moral and life dilemmas without relying on generic, unsupported chatbot advice. 
Many people ask AI systems questions like “Should I lie to avoid hurting someone?”, “How do I handle anxiety?”, or “Is this business decision ethical?” A normal chatbot may answer fluently, but it can hallucinate, ignore cultural or spiritual grounding, expose private dilemmas to cloud systems, or give advice without evidence. Anayaa focuses on this gap: it gives guidance that is scripture-grounded, privacy-conscious, auditable, and locally runnable.
This is important because moral guidance is sensitive. Users need more than fast answers; they need answers that are calm, explainable, relevant to the actual dilemma, and supported by trusted texts. Anayaa makes the reasoning process safer by retrieving scripture evidence, checking whether the answer is grounded, and showing only user-facing guidance rather than internal agent logs.

## Solution

Multi-agentic RAG is useful here because the problem is not a single-step “generate an answer” task. Anayaa has to understand the dilemma, decide what moral concepts matter, retrieve relevant scripture, recover if retrieval is weak, optionally let the user review the evidence, synthesize the final guidance, and audit the result.

Anayaa uses agents because each step needs a different kind of intelligence:

- Query Rewriter: cleans up vague or malformed user questions and frames them as moral questions.
- Optimizer: prepares efficient semantic cache keys and optimized prompts.
- Strategic Planner Agent: identifies important concepts such as duty, truth, restraint, compassion, anxiety, greed, or discipline.
- ReAct Reasoner: checks whether the first retrieval pass is good enough and can retry with better search concepts.
- MCP Retriever Tool Agent: searches scripture through a controlled tool boundary using Milvus hybrid search, graph expansion, and reranking.
- Human-in-the-loop Review: in Interactive Guidance mode, the user can approve concepts, select scripture candidates, or manually add scripture before synthesis.
- Synthesizer Agent: creates the final guidance in sections: Summary, Reflection, Judgement, Next step, and Scripture grounding.
- G-Eval / Audit Agent: checks faithfulness, grounding, relevance, harmlessness, privacy, dharma alignment and displays Sustainable Computing metrics and information
- Finalizer: returns complete guidance, an approval checkpoint, or a clear failure message if retrieval or synthesis is not safe enough.

Agents uniquely help because moral guidance needs controlled collaboration between reasoning, retrieval, human review, synthesis, and auditing. A single LLM call cannot reliably do all of that with the same safety and traceability.

The project is built for local use with limited resources.

CodeCarbon Real-Time Audit (Sustainable Computing)
Anayaa promotes eco-conscious and green computing:
Environmental Impact Tracking: Displays real-time metrics showing the cumulative carbon footprint (in kilograms) and total edge compute energy consumed (in Watt-hours) during local model execution. Per request metrics can be viewed in the Eco Audit tab.
Power Draft Monitoring: Shows active CPU/GPU power consumption levels to highlight the efficiency benefits of lightweight, quantized on-device architectures.

- Backend: FastAPI, PostgreSQL, Redis, Milvus Lite, MCP, Google ADK, Ollama
- Frontend: React 19, TypeScript, Vite 6, Tailwind CSS, lucide-react
- Retrieval: scripture JSON corpus, ONNX local embeddings, Milvus hybrid search, graph expansion, reranking
- Safety: sanitizer, regex firewall, PII scrubber, MCP tool allowlist, G-Eval style audit, deterministic grounding checks
- Auth: PostgreSQL-backed users, salted PBKDF2 password hashes, JWT sessions, local reset-code flow
- Local models: `gemma2:2b` for lightweight classification, `qwen3:4b` for planning/retry planning/judging, and `llama3.2:3b` for final guidance synthesis



<img width="1899" height="987" alt="image" src="https://github.com/user-attachments/assets/99f1f747-54ac-4813-8e7e-b1cd63812151" />
<img width="1124" height="1029" alt="image" src="https://github.com/user-attachments/assets/ad338070-759d-4af5-a44f-b3c32165b0eb" />
<img width="1127" height="1034" alt="image" src="https://github.com/user-attachments/assets/1581e3fd-b63e-4b6b-8e91-ab2e2cae4c74" />
<img width="829" height="1031" alt="image" src="https://github.com/user-attachments/assets/8f809b28-650b-4cc3-98ac-2d94ab7e11e2" />





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

## Architecture

```text
React + Vite frontend
    |
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
    |      |-- milvus_hybrid_search
    |      |-- graph_expand
    |      |-- rerank_candidates_tool
    |      v
    |   Milvus Lite scripture_verses collection
    |
    |-- optional pre-synthesis human review
    |-- Ollama synthesis with section-contract cleanup
    |-- LLM judge and deterministic grounding contract
    |-- PostgreSQL persistence
    |-- Redis semantic cache and session state
```
```mermaid
flowchart TD
    A["React + Vite Frontend"] --> B["FastAPI Backend API"]

    B --> C["Auth: PostgreSQL Users + JWT Sessions"]
    B --> D["Security Layer: Sanitizer + Regex Firewall + PII Scrubber"]
    D --> E["Query Rewriter + Optimizer"]
    E --> F["Planner Agent"]

    F --> G["Bounded ReAct Reasoner"]
    G --> H["MCP Retrieval Client"]
    H --> I["MCP Stdio Retrieval Server"]

    I --> J["Milvus Lite Vector Store"]
    I --> K["Scripture Corpus JSON"]
    I --> L["Graph Expansion + Reranking"]

    L --> M{"Interactive Guidance?"}
    M -->|Yes| N["Human Review: Concepts + Scripture Selection"]
    M -->|No| O["Synthesizer Agent"]

    N --> O
    O --> P["G-Eval Judge + Deterministic Grounding Checks"]
    P --> Q["Finalizer"]
    Q --> R["User-Facing Guidance UI"]

    B --> S["Redis Cache + Rate Limits"]
    B --> T["Eco Metrics + Audit Logs"]
```
Runtime retrieval goes through the MCP tool boundary. The FastAPI request path does not open `MilvusStore` directly for retrieval. The MCP client allowlists only:

- `milvus_hybrid_search`
- `graph_expand`
- `rerank_candidates_tool`

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

Planner and synthesizer failures are surfaced as explicit workflow statuses instead of silently falling back to deterministic answers. This keeps the system honest when a local model is unavailable, returns invalid JSON, or produces a draft that fails the guidance contract.

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
|   |-- anayaa          # product-style local CLI: setup, serve, doctor, stop, clean
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

# Verify installation
python3 --version
node --version
pg_isready -h 127.0.0.1 -p 5432
redis-cli ping
ollama --version

The startup scripts expect PostgreSQL at `127.0.0.1:5432`, Redis at `redis://127.0.0.1:6379/0`, and Ollama at `http://127.0.0.1:11434` unless overridden in `backend/.env`.

## Local Setup

Anayaa is local-first. The normal product-style path is one setup command, then one serve command.

```bash
./scripts/anayaa setup
./scripts/anayaa serve
```

Open:

- App: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/api/health`
- Deep health: `http://127.0.0.1:8000/api/health/deep`

`./scripts/anayaa setup` is the one-time online setup. Keep internet access on for this step because it prepares PostgreSQL, installs Python/npm dependencies, builds the React frontend, pulls local Ollama models, caches and exports ONNX embedding assets, and seeds retrieval. This is also the command to run again after `./scripts/anayaa clean --all --yes`, because `--all` removes storage and dependency folders.

`./scripts/anayaa serve` starts the local runtime. It works for normal offline/local use after setup because `OFFLINE_MODE=true` uses cached dependencies, built frontend assets, local Ollama models, ONNX embeddings, and local Milvus Lite data. If you intentionally want serve to repair missing online assets, run:

```bash
./scripts/anayaa serve --online
```

Useful product-style commands:

```bash
./scripts/anayaa doctor
./scripts/anayaa stop
./scripts/anayaa clean
```

`./scripts/anayaa doctor` checks the local runtime and reports exactly what is missing. `./scripts/anayaa stop` stops Anayaa app processes without deleting cached models, local data, or the built frontend. `./scripts/anayaa clean` delegates to the cleanup script for generated files and optional storage/dependency cleanup.

`scripts/start-backend.sh` creates `backend/.env` from `backend/.env.example` when needed, generates a safe local `JWT_SECRET`, checks PostgreSQL and Redis, ensures Ollama models are available, verifies Milvus Lite, seeds empty retrieval data, runs lightweight schema migrations such as user reset columns, and starts FastAPI on port 8000. The built frontend is served by FastAPI from `frontend/dist`.

With `OFFLINE_MODE=true`, backend startup does not install missing Python packages from the internet. It uses the existing `backend/anayaa` virtual environment created by `./scripts/setup-online.sh`. If you ran `./scripts/free-resources.sh --all --yes`, reconnect to Wi-Fi and run `./scripts/setup-online.sh` before starting the backend again.

Milvus Lite must be able to bind a local Unix socket while seeding and serving `backend/data/milvus.db`. Run setup and backend startup from a normal macOS Terminal window. Restricted or sandboxed shells can fail with `Operation not permitted` or `Fail connecting to server on unix:...milvus.db.sock`.

Milvus seeding is idempotent. If the Milvus collection already has vectors, backend startup skips reloading scripture embeddings. If the collection is empty, startup runs `backend/scripts/seed_milvus.py`. In normal offline runtime this works only if the embedding model was already cached by `./scripts/setup-online.sh`; if the cache is missing, `scripts/start-backend.sh` stops with a clear message telling you to reconnect to Wi-Fi and run `./scripts/setup-online.sh`.

`backend/scripts/seed_milvus.py` itself does not perform full online setup. It upserts scripture rows into PostgreSQL, avoids duplicate graph edges, and seeds or recreates Milvus vectors when the stored vector count does not match the local scripture corpus. Dependency installation, Hugging Face embedding downloads, Ollama model pulls, and first-time cache warming belong to `./scripts/setup-online.sh`.

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

For frontend/backend development, you can still run the old two-process Vite flow:

```bash
./scripts/start-backend.sh
./scripts/start-frontend.sh
```

The development frontend runs at `http://127.0.0.1:5173` and proxies API calls to the backend at `http://127.0.0.1:8000`.

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
| `EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Source embedding model exported during setup |
| `EMBEDDING_BACKEND` | `onnx` | Uses exported ONNX embeddings at runtime |
| `EMBEDDING_ONNX_DIR` | `data/onnx_embeddings` | Local generated ONNX embedding assets |
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
  "preSynthesisVerification": true
}
```

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

```bash
./scripts/pre-merge-checks.sh
```

That script runs:

- Python compile checks for `backend/app` and `backend/tests`
- Backend tests
- Frontend production build

Useful targeted checks while developing:

```bash
cd backend
anayaa/bin/python -m pytest tests/test_llm_strategic_planner.py tests/test_llm_react_retry_planner.py tests/test_guidance_section_contract.py tests/test_grounding_contract.py tests/test_guidance_reasons.py tests/test_hitl_compile_audit_query.py
```

```bash
cd frontend
npm run build
```

## Local Operations

Free common local development resources:

```bash
./scripts/free-resources.sh
```

The cleanup script is intentionally tracked in git. It removes ignored/generated local artifacts such as Python caches, `.pytest_cache`, `.DS_Store`, Vite cache, `frontend/dist`, local startup logs, and orphaned Anayaa backend/frontend/MCP processes.

Use stronger cleanup only when you really want to reclaim more local resources:

```bash
./scripts/free-resources.sh --all --yes
```

`--all` enables `--services`, `--storage`, and `--deps`. That can stop shared local PostgreSQL, Redis, Ollama, and Milvus ports; wipe Anayaa Redis/PostgreSQL app data; remove the local Milvus Lite DB; and delete dependency folders such as `backend/anayaa`, legacy local virtualenv folders, and `frontend/node_modules`. After `--storage` or `--all`, reconnect to Wi-Fi and run setup/startup again so dependencies, cached assets, and retrieval data are restored:

```bash
./scripts/anayaa setup
./scripts/anayaa serve
```

Run load tests:

```bash
export ANAYAA_LOAD_TEST_EMAIL="code.test@example.com"
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
