-- One LLM review per CASE, replacing three calls per conversation.
--
-- case_summaries (013) is keyed by conversation_id, which is why the summary regenerated
-- whenever ANY of a customer's cases received a message: the cache compares the
-- conversation's newest turn, so a message on a fraud dispute invalidated the summary of
-- an unrelated loan query and re-ran all three calls. Measured on the live customer: 30
-- turns across 8 tickets behind one cache row.
--
-- Keyed by ticket_id instead. A message on case A invalidates case A alone; every other
-- case keeps serving its stored review and spends nothing. This is what makes the
-- per-case cards cheaper than the conversation-wide ones they replace, not just better
-- scoped - the review is regenerated per case that actually changed, rather than per
-- conversation that changed anywhere.
--
-- Holds all three sections from the single case_review call (see case_reviewer.py):
-- situation for the Case Summary card, actions for Suggested Actions, offers for
-- Suggested Offers. Storing them together is the point - they came from one response,
-- and splitting them across tables would let the three cards disagree about which
-- generation they are showing.
CREATE TABLE IF NOT EXISTS case_reviews (
    ticket_id TEXT PRIMARY KEY REFERENCES tickets(ticket_id),
    conversation_id TEXT NOT NULL,
    -- The case's OWN newest turn, not the conversation's. The comparison that decides
    -- whether this row is still current.
    latest_turn_id TEXT NOT NULL,
    situation TEXT NOT NULL DEFAULT '',
    actions_json TEXT NOT NULL DEFAULT '[]',
    offers_json TEXT NOT NULL DEFAULT '[]',
    -- Why a section is empty: a gated review and a failed one must never be stored as
    -- "nothing to say". Only successful runs are written at all, but a run where the
    -- sentiment gate closed the offers section is a success with a reason.
    offers_suppressed TEXT,
    model TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_case_reviews_conversation ON case_reviews(conversation_id);
