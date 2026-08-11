-- Human-in-the-loop reply drafts.
-- When the review gate holds an AI reply (see services/workflow_service/review_gate.py),
-- the AI's answer is stored here as a pending draft for a human agent to edit and send
-- manually, instead of being auto-delivered to the customer.
CREATE TABLE IF NOT EXISTS reply_drafts (
    draft_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    ticket_id TEXT,
    channel TEXT NOT NULL,              -- channel the held query arrived on (web_chat/whatsapp/email)
    channel_identifier TEXT,            -- customer's channel address (phone/email/web-session) for manual delivery
    provider TEXT,                      -- inbound provider, so the manual send uses the same delivery path
    inbound_turn_id TEXT,               -- the customer turn this draft answers (if known)
    draft_text TEXT NOT NULL,           -- the AI's proposed answer (editable)
    hold_reason TEXT NOT NULL DEFAULT '',   -- friendly label, e.g. "Assisted resolution (L2)"
    reason_code TEXT NOT NULL DEFAULT '',   -- stable code, e.g. "assisted_resolution_required:card_management"
    status TEXT NOT NULL DEFAULT 'pending', -- pending | sent | discarded
    sent_text TEXT,                     -- the final text the agent actually sent (may differ from draft_text)
    decided_by TEXT,
    decided_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reply_drafts_conversation ON reply_drafts(conversation_id, status);
CREATE INDEX IF NOT EXISTS idx_reply_drafts_status ON reply_drafts(status, created_at);
