ALTER TABLE tickets ADD COLUMN external_ticket_id TEXT;
ALTER TABLE tickets ADD COLUMN external_ticket_url TEXT;
ALTER TABLE tickets ADD COLUMN crm_sync_status TEXT NOT NULL DEFAULT 'not_configured';
ALTER TABLE tickets ADD COLUMN crm_sync_error TEXT;
ALTER TABLE tickets ADD COLUMN approval_status TEXT NOT NULL DEFAULT 'not_required';
ALTER TABLE tickets ADD COLUMN escalation_reason TEXT;
ALTER TABLE tickets ADD COLUMN sla_due_at TEXT;
ALTER TABLE tickets ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS ticket_events (
    ticket_event_id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id),
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ticket_events_ticket_created
ON ticket_events(ticket_id, created_at);

CREATE INDEX IF NOT EXISTS idx_tickets_external_ticket
ON tickets(external_ticket_id);
