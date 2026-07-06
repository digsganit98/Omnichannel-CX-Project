PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    display_name TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channel_identities (
    identity_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    channel TEXT NOT NULL,
    identifier TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(channel, identifier)
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    summary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_turns (
    turn_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    channel TEXT NOT NULL,
    direction TEXT NOT NULL,
    text TEXT NOT NULL,
    external_message_id TEXT,
    subject TEXT,
    intent TEXT,
    urgency TEXT,
    resolved INTEGER,
    ticket_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    delivery_status TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    intent TEXT NOT NULL,
    priority TEXT NOT NULL,
    assigned_team TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    provider TEXT NOT NULL,
    external_message_id TEXT NOT NULL,
    response_json TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY(provider, external_message_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    customer_id TEXT,
    conversation_id TEXT,
    message_id TEXT,
    intent TEXT,
    ticket_id TEXT,
    channel TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retrieval_evidence (
    evidence_id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES conversation_turns(turn_id),
    source TEXT NOT NULL,
    document_version TEXT,
    chunk_text TEXT NOT NULL,
    score REAL NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turns_conversation_created
ON conversation_turns(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_tickets_conversation_status
ON tickets(conversation_id, status);

CREATE INDEX IF NOT EXISTS idx_audit_correlation
ON audit_events(correlation_id, created_at);
