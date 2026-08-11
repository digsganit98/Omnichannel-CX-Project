CREATE TABLE IF NOT EXISTS llm_usage_events (
    event_id TEXT PRIMARY KEY,
    correlation_id TEXT,
    conversation_id TEXT,
    customer_id TEXT,
    message_id TEXT,
    channel TEXT,
    agent TEXT,
    operation TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    llm_used INTEGER NOT NULL DEFAULT 0,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL NOT NULL DEFAULT 0,
    latency_ms REAL,
    status TEXT NOT NULL,
    error TEXT,
    intent TEXT,
    resolution_level TEXT,
    ticket_id TEXT,
    retrieval_backend TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_created
ON llm_usage_events(created_at);

CREATE INDEX IF NOT EXISTS idx_llm_usage_correlation
ON llm_usage_events(correlation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_llm_usage_conversation
ON llm_usage_events(conversation_id, created_at);
