-- LLM-grouped customer record for the right-panel Customer Context tabs.
--
-- Same on-demand caching idea as 013_case_summaries, keyed differently on purpose.
-- A case summary goes stale when a TURN arrives, so it keys on latest_turn_id. A
-- customer context goes stale when a FIELD changes - a repaid card, a settled claim,
-- a new transaction - which no turn id tracks. So this keys on a fingerprint of the
-- record the summary was built from: same record, serve the cached row; any field
-- different, the hash differs and the route regenerates. Cost tracks agent attention
-- and real data change, not message volume.
--
-- categories_json holds the whole {category_key: [{label, value, sub?}]} document.
-- Storing it as one blob rather than a row per item is deliberate: it is written and
-- read as a unit, never queried by field, and the endpoint re-validates the shape on
-- read anyway.
CREATE TABLE IF NOT EXISTS customer_context (
    customer_id TEXT PRIMARY KEY,
    record_hash TEXT NOT NULL,
    categories_json TEXT NOT NULL DEFAULT '{}',
    model TEXT,
    created_at TEXT NOT NULL
);
