-- Records that an opportunity evaluation RAN, so it is not repeated unchanged.
--
-- agent_assist_recommendations already stores the offers an evaluation produced, but it
-- cannot serve as the cache: an evaluation that produces NO offers (the common case -
-- the model returns [] for a customer with nothing to pitch) writes no row at all, so
-- there is nothing to distinguish "never evaluated" from "evaluated, nothing to offer".
-- The endpoint therefore re-ran a ~1000-token Groq call on every panel render, including
-- the inbox poll's re-render: 53 calls in one day with zero customer messages.
--
-- Keyed on a fingerprint of the inputs that can change the answer - the customer's graph
-- records, their turn count, and the offers already suggested. Same inputs -> serve the
-- stored rows and spend nothing; a new message or a changed record -> new hash, re-run.
CREATE TABLE IF NOT EXISTS opportunity_evaluations (
    conversation_id TEXT PRIMARY KEY,
    input_hash TEXT NOT NULL,
    suppressed TEXT,
    created_at TEXT NOT NULL
);
