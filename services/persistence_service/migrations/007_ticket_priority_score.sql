ALTER TABLE tickets ADD COLUMN priority_score REAL NOT NULL DEFAULT 0;
ALTER TABLE tickets ADD COLUMN priority_breakdown_json TEXT NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_tickets_priority_score
ON tickets(status, priority_score DESC);
