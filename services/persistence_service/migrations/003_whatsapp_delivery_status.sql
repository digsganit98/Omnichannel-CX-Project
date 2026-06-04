CREATE TABLE IF NOT EXISTS whatsapp_delivery_statuses (
    status_event_id TEXT PRIMARY KEY,
    provider_message_id TEXT NOT NULL,
    status TEXT NOT NULL,
    recipient_id TEXT,
    conversation_id TEXT,
    turn_id TEXT,
    timestamp TEXT,
    error_code TEXT,
    error_title TEXT,
    error_details TEXT,
    raw_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_delivery_provider_message
ON whatsapp_delivery_statuses(provider_message_id, created_at);

CREATE INDEX IF NOT EXISTS idx_turns_external_message
ON conversation_turns(external_message_id);
