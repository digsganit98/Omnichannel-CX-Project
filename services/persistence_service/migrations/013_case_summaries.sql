-- Agent-facing case summaries, generated on demand when an agent opens a conversation.
--
-- Deliberately NOT the existing conversations.summary column. That field is a raw
-- pipe-delimited log of the last 6 turns, written on every message and fed to the LLM
-- only as a fallback when recent_turns is empty (see groq_generator._format_conversation_
-- history). It is machine input; this is human output. Overloading one column with both
-- would make every read ambiguous about which it was getting.
--
-- Keyed by conversation with the turn id it was generated from: a summary is only valid
-- for the conversation state it described, so a new turn makes the cached row stale
-- without needing to delete it. The route compares latest_turn_id and regenerates on
-- mismatch, which keeps cost proportional to agent attention rather than message volume.
CREATE TABLE IF NOT EXISTS case_summaries (
    conversation_id TEXT PRIMARY KEY REFERENCES conversations(conversation_id),
    latest_turn_id TEXT NOT NULL,
    situation TEXT NOT NULL DEFAULT '',
    open_items_json TEXT NOT NULL DEFAULT '[]',
    last_contact TEXT NOT NULL DEFAULT '',
    model TEXT,
    created_at TEXT NOT NULL
);
