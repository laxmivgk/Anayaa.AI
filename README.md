
# Anayaa.AI - Kaggle Capstone Submission for Agents for Good
## License & AI Safety Notice

This project's custom code, notebooks, and architecture are licensed under the [Creative Commons Attribution 4.0 International License](./LICENSE.txt) per Kaggle Capstone requirements.

However, this project interfaces with local foundational models (Meta Llama 3.2, Google Gemma, and Alibaba Qwen) and tools which are independently governed by their respective community licenses and commercial terms. The CC-BY 4.0 license applies strictly to the logic, frontend, and pipeline configurations authored in this repository.

# Anayaa.AI
Anayaa.AI is a local-first, resource-aware scripture-grounded guidance app for moral and life dilemmas. It uses lightweight local models, retrieval caching, and per-request Eco Audit metrics to make compute cost visible and reduce unnecessary generation. Anayaa is eco-conscious, not zero-impact: local AI still uses disk, memory, and energy.

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
- G-Eval / Audit Agent: checks faithfulness, grounding, relevance, harmlessness, privacy, dharma alignment and displays resource-aware compute metrics
- Finalizer: returns complete guidance, an approval checkpoint, or a clear failure message if retrieval or synthesis is not safe enough.

Agents uniquely help because moral guidance needs controlled collaboration between reasoning, retrieval, human review, synthesis, and auditing. A single LLM call cannot reliably do all of that with the same safety and traceability.

The project is built for local use with limited resources.

CodeCarbon Real-Time Audit (Resource-Aware Computing)
Anayaa promotes eco-conscious measurement rather than a zero-impact claim:
Environmental Impact Tracking: Displays estimated cumulative carbon footprint (in kilograms) and total edge compute energy consumed (in Watt-hours) during local model execution. Per-request metrics can be viewed in the Eco Audit tab.
Power Draft Monitoring: Shows active CPU/GPU power estimates to make local compute cost visible and encourage lightweight, quantized on-device architectures where practical.

- Backend: FastAPI, PostgreSQL, Redis, Milvus Lite, MCP, Google ADK, Ollama
- Frontend: React 19, TypeScript, Vite 6, Tailwind CSS, lucide-react
- Retrieval: scripture JSON corpus, ONNX local embeddings, Milvus hybrid search, graph expansion, reranking
- Safety: sanitizer, regex firewall, deterministic PII scrubber with local NER support, MCP tool allowlist, G-Eval style audit, deterministic grounding checks
- Auth: PostgreSQL-backed users, salted PBKDF2 password hashes, JWT sessions, server-side password reset tokens delivered by SMTP email or local terminal fallback
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

1. The user logs in with an email address and password. A new email self-registers on first login, while existing emails must use their saved password. Password fields include an eye icon for reveal/hide.
2. The Active Pathway tab starts with a choice: `New dilemma` or, when recent local history exists, `Follow-up dilemma`.
3. After the user chooses a mode, the query box receives focus and accepts the dilemma. The box has a 4000-character limit and locks after an answer loads.
4. `New dilemma` sends a standalone query. `Follow-up dilemma` sends up to three scrubbed recent local questions as bounded `previousContext`; it is not full hidden memory.
5. The user can choose `The Interactive Guidance` or `The Guidance`.
6. `The Interactive Guidance` pauses before synthesis so the user can adjust concepts, select scripture candidates, or add a manual scripture. Clicking `Compile guidance` locks the interactive controls while the final guidance is generated.
7. `The Guidance` runs the same pipeline directly without the pre-synthesis review pause.
8. The login page includes `Forgot password?`; the reset form tells users to enter an email that already exists in Anayaa. Reset instructions are emailed when SMTP is configured, or printed to the backend terminal in local mode only.
9. Completed guidance can be marked `Helpful` or `Needs work`; the backend persists feedback for future planner tone and summary context.
10. Browser Back from authenticated tabs logs the user out and returns to the login page.
11. The UI shows only user-facing guidance. Internal guidance validation details are not shown.
12. Scripture Evidence shows only citations that were actually used in the final answer.

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
    |-- sanitizer -> regex firewall -> PII scrubber + local NER
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
    B --> D["Security Layer: Sanitizer + Regex Firewall + PII Scrubber + Local NER"]
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

New-dilemma queries are standalone. Follow-up mode can send a bounded `previousContext` payload containing up to three scrubbed recent local questions; the backend sanitizes and firewalls each item before using it to contextualize the rewritten query.

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
|   |   |-- security/        # sanitizer, firewall, privacy scrubber, local NER
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
|   |-- install-anayaa.sh
|   |-- setup-online.sh
|   |-- setup_postgres.sh
|   |-- start-backend.sh
|   |-- start-frontend.sh
|   |-- run-load-test.sh
|   |-- pre-merge-checks.sh
|   `-- free-resources.sh
|-- INSTALL.md
|-- PRIVACY.md
|-- DISCLAIMER.md
`-- README.md
```

## Local-First Public Beta

For an Ollama-style public beta, Anayaa is meant to be installed and run on the user's own machine. The local browser UI talks to `127.0.0.1`, while PostgreSQL, Redis, Milvus Lite, embeddings, scripture data, and Ollama models stay local by default.

First-time users start with:

```bash
curl -sSL https://raw.githubusercontent.com/laxmivgk/Anayaa.AI/v0.1.0-local-beta/scripts/install-anayaa.sh | bash
anayaa setup
anayaa serve
```

The installer downloads Anayaa into `~/.anayaa/Anayaa.AI` and links the `anayaa` command into `~/.local/bin`. If your shell cannot find `anayaa` after install, open a new terminal or run:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

For developer checkouts, run `./scripts/install-anayaa.sh` from the cloned repo instead of the release `curl` command.

Expected timing:

| Step | Typical time |
| --- | ---: |
| First-time `anayaa setup` | 20-60 minutes |
| Slower WSL or older machines | 60-90 minutes |
| Daily `anayaa serve` after setup | 1-2 minutes |

`anayaa setup` is the required bootstrap step for first-time users. `anayaa serve` is the daily local runtime command after setup has built the frontend, installed dependencies, pulled Ollama models, cached embeddings, and seeded retrieval.

Read:

- [INSTALL.md](./INSTALL.md) for macOS, Linux, and Windows WSL2 setup.
- [PRIVACY.md](./PRIVACY.md) for local-first data behavior.
- [DISCLAIMER.md](./DISCLAIMER.md) before using Anayaa for sensitive real-world dilemmas.

## Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL running locally
- Redis running locally
- Ollama installed locally
- Enough disk space for local Python packages, embedding assets, Milvus Lite data, and Ollama models

Windows is supported through WSL2 Ubuntu. Run the same Anayaa commands from the WSL shell; the setup wrapper can start local services through Homebrew on macOS or `service`/`systemctl` on WSL/Linux.

### Verify installation

If setup fails, these commands help confirm the local prerequisites:

```bash
python3 --version
node --version
pg_isready -h 127.0.0.1 -p 5432
redis-cli ping
ollama --version
```

The startup scripts expect PostgreSQL at `127.0.0.1:5432`, Redis at `redis://127.0.0.1:6379/0`, and Ollama at `http://127.0.0.1:11434` unless overridden in `backend/.env`.

## Local Setup

Anayaa is local-first. The normal product-style path is install, setup, then serve.

```bash
curl -sSL https://raw.githubusercontent.com/laxmivgk/Anayaa.AI/v0.1.0-local-beta/scripts/install-anayaa.sh | bash
anayaa setup
anayaa serve
```

From a cloned checkout, use `./scripts/install-anayaa.sh` instead of the release `curl` command.

Open:

- App: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/api/health`
- Deep health: `http://127.0.0.1:8000/api/health/deep`

`anayaa setup` is the one-time online setup. Keep internet access on for this step because it prepares PostgreSQL, installs Python/npm dependencies, builds the React frontend, pulls local Ollama models, caches and exports ONNX embedding assets, and seeds retrieval. Run it again after updating `backend/data/scriptures.json`; setup checks the stored corpus count and checksum, then rebuilds Milvus embeddings when the local corpus changed. This is also the command to run again after `anayaa clean --all --yes`, because `--all` removes storage and dependency folders. First-time users should expect setup to take 20-60 minutes, mostly because of dependency installs, model pulls, embedding export, and retrieval seeding.

`anayaa serve` starts the local runtime. It works for normal offline/local use after setup because `OFFLINE_MODE=true` uses cached dependencies, built frontend assets, local Ollama models, ONNX embeddings, and local Milvus Lite data. If `serve` reports missing frontend assets, models, embeddings, or Milvus data, run `anayaa setup` once before serving again. If you intentionally want serve to repair missing online assets, run:

```bash
anayaa serve --online
```

Useful product-style commands:

```bash
anayaa doctor
anayaa release-check
anayaa stop
anayaa clean
```

`anayaa doctor` checks the local runtime and reports exactly what is missing, including WSL `/mnt/...` installs, CRLF script line endings, and missing executable bits. `anayaa release-check` runs doctor plus compile, backend test, and frontend build checks for a local release candidate. `anayaa stop` stops Anayaa app processes without deleting cached models, local data, or the built frontend. `anayaa clean` delegates to the cleanup script for generated files and optional storage/dependency cleanup.

`scripts/start-backend.sh` creates `backend/.env` from `backend/.env.example` when needed, generates a safe local `JWT_SECRET`, checks PostgreSQL and Redis, ensures Ollama models are available, verifies Milvus Lite, seeds empty retrieval data, runs lightweight schema migrations such as user reset columns, and starts FastAPI on port 8000. The built frontend is served by FastAPI from `frontend/dist`.

With `OFFLINE_MODE=true`, backend startup does not install missing Python packages from the internet. It uses the existing `backend/anayaa` virtual environment created by `./scripts/anayaa setup`. If you ran `./scripts/free-resources.sh --all --yes`, reconnect to Wi-Fi and run `./scripts/anayaa setup` before starting the app again.

Milvus Lite must be able to bind a local Unix socket while seeding and serving `backend/data/milvus.db`. Run setup and backend startup from a normal macOS Terminal or WSL/Linux shell. Restricted or sandboxed shells can fail with `Operation not permitted` or `Fail connecting to server on unix:...milvus.db.sock`.

Milvus seeding is idempotent. If the Milvus collection already has vectors, backend startup skips reloading scripture embeddings. If the collection is empty, startup runs `backend/scripts/seed_milvus.py`. In normal offline runtime this works only if the embedding model was already cached by `./scripts/anayaa setup`; if the cache is missing, `scripts/start-backend.sh` stops with a clear message telling you to reconnect to Wi-Fi and run `./scripts/anayaa setup`.

`backend/scripts/seed_milvus.py` itself does not perform full online setup. It checks the stored corpus status, upserts scripture rows into PostgreSQL, avoids duplicate graph edges, and seeds or recreates Milvus vectors when the stored vector count or checksum does not match the local scripture corpus. Dependency installation, Hugging Face embedding downloads, Ollama model pulls, and first-time cache warming belong to `./scripts/anayaa setup`.

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
| `APP_ENV` | `local` | Runtime mode; `production` requires configured password-reset delivery |
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
| `PASSWORD_RESET_BASE_URL` | `http://127.0.0.1:8000` | Base URL used in emailed password-reset links |
| `SMTP_HOST` | empty | SMTP host for production password reset email |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USERNAME` | empty | SMTP login username, if required |
| `SMTP_PASSWORD` | empty | SMTP login password, if required |
| `SMTP_FROM` | empty | From address for password-reset email |
| `SMTP_USE_TLS` | `false` | Use implicit TLS/SMTPS |
| `SMTP_STARTTLS` | `true` | Upgrade SMTP connection with STARTTLS |
| `PII_NER_ENABLED` | `true` | Enables local named-entity detection for privacy scrubbing |
| `PII_NER_MODEL` | empty | Optional cached Hugging Face NER model; empty uses the lightweight local recognizer |
| `PII_NER_LOCAL_FILES_ONLY` | `true` | Loads the optional NER model only from local cache |
| `PII_NER_FALLBACK_ENABLED` | `true` | Falls back to the lightweight recognizer if the optional NER model is unavailable |
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

If a user forgets their password, click `Forgot password?` on the login screen and request reset instructions using an email that already exists in Anayaa. The API response remains generic and does not reveal whether the email exists. When the email does exist, Anayaa creates a single-use random reset token, stores only its hash in PostgreSQL, and expires it after 15 minutes. In local mode without SMTP, the backend prints the reset code and link to the local terminal. In production, configure `SMTP_HOST` and `SMTP_FROM` so Anayaa emails the reset code/link; `APP_ENV=production` refuses terminal-only reset delivery.

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
  "preSynthesisVerification": true,
  "previousContext": [
    {
      "question": "How can I be honest with a friend without being harsh?",
      "timestamp": "2026-07-05T12:00:00.000Z"
    }
  ]
}
```

Use `preSynthesisVerification: true` for Interactive Guidance and `false` for direct Guidance. Omit `previousContext` or send an empty list for a new dilemma; send up to three recent scrubbed questions for follow-up mode.

`POST /api/auth/login` self-registers unknown emails with the submitted password. Existing emails require the stored password. `POST /api/auth/password-reset/request` does not reveal whether an email exists; when it does, reset instructions are delivered by configured SMTP email or, in local mode only, printed to the backend terminal.

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
- `previousContextUsed`
- `previousContextQuestion`

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

For normal cleanup, use the product CLI:

```bash
./scripts/anayaa clean
```

This is the safe daily cleanup path. It removes ignored/generated local artifacts such as Python caches, `.pytest_cache`, `.DS_Store`, Vite cache, `frontend/dist`, local startup logs, and orphaned Anayaa backend/frontend/MCP processes. It does not wipe local PostgreSQL/Redis app data, Milvus Lite data, dependency folders, or shared local services.

Use full reset cleanup only when you really want to start over from scratch:

```bash
./scripts/anayaa clean --all --yes
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
