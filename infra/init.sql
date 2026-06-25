-- Anayaa.AI PostgreSQL schema

CREATE TABLE IF NOT EXISTS corpus_status (
    id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    ready BOOLEAN NOT NULL DEFAULT FALSE,
    verse_count INT NOT NULL DEFAULT 0,
    last_seed_at TIMESTAMPTZ,
    seed_version TEXT,
    seed_checksum TEXT
);

INSERT INTO corpus_status (id, ready, verse_count) VALUES (1, FALSE, 0)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS scriptures (
    id TEXT PRIMARY KEY,
    faith TEXT NOT NULL,
    source TEXT NOT NULL,
    chapter TEXT NOT NULL,
    verse TEXT NOT NULL,
    original_text TEXT,
    translation TEXT NOT NULL,
    context TEXT NOT NULL,
    keywords TEXT[] NOT NULL DEFAULT '{}',
    milvus_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kg_entities (
    id SERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    faith TEXT,
    UNIQUE(entity_type, name, faith)
);

CREATE TABLE IF NOT EXISTS kg_edges (
    id SERIAL PRIMARY KEY,
    from_entity_id INT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    to_entity_id INT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    relation TEXT NOT NULL,
    scripture_id TEXT REFERENCES scriptures(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS turns (
    id SERIAL PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id),
    request_id TEXT NOT NULL,
    scrubbed_query TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_traces (
    id SERIAL PRIMARY KEY,
    request_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}',
    duration_ms INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedback_records (
    request_id TEXT PRIMARY KEY,
    user_email TEXT NOT NULL,
    query TEXT,
    status TEXT NOT NULL CHECK (status IN ('FOLLOWED_DHARMA', 'STRAYED_FROM_PATH')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS request_eco_metrics (
    id SERIAL PRIMARY KEY,
    request_id TEXT NOT NULL,
    user_email TEXT NOT NULL,
    agent_stage TEXT NOT NULL,
    energy_wh DOUBLE PRECISION NOT NULL,
    co2_kg DOUBLE PRECISION NOT NULL,
    cpu_watts DOUBLE PRECISION,
    gpu_watts DOUBLE PRECISION,
    duration_ms INT,
    cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_eco_rollups (
    id SERIAL PRIMARY KEY,
    rollup_date DATE NOT NULL,
    user_email TEXT NOT NULL,
    total_energy_wh DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_co2_kg DOUBLE PRECISION NOT NULL DEFAULT 0,
    query_count INT NOT NULL DEFAULT 0,
    UNIQUE(rollup_date, user_email)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    request_id TEXT NOT NULL,
    g_eval_scores JSONB NOT NULL,
    judge_model TEXT,
    passed BOOLEAN NOT NULL,
    raw_rationale TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hitl_checkpoints (
    workflow_run_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    user_email TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'revised')),
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resumed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_scriptures_faith ON scriptures(faith);
CREATE INDEX IF NOT EXISTS idx_scriptures_keywords ON scriptures USING GIN(keywords);
CREATE INDEX IF NOT EXISTS idx_eco_daily ON daily_eco_rollups(rollup_date, user_email);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_request_eco_metrics_created_at ON request_eco_metrics(created_at);
CREATE INDEX IF NOT EXISTS idx_hitl_checkpoints_terminal_retention
    ON hitl_checkpoints(status, resumed_at, created_at);
CREATE INDEX IF NOT EXISTS idx_turns_created_at ON turns(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_records_user_email ON feedback_records(user_email);
