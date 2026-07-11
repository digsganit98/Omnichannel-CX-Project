CREATE TABLE IF NOT EXISTS agent_assist_recommendations (
    recommendation_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    ticket_id TEXT,
    customer_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    confidence REAL NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    decided_by TEXT,
    decided_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nba_ticket ON agent_assist_recommendations(ticket_id, status);
CREATE INDEX IF NOT EXISTS idx_nba_conversation ON agent_assist_recommendations(conversation_id, status, action_type);
