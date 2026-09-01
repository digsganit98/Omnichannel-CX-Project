-- 018: add tickets.last_activity_at - "when did a message last land on this thread".
--
-- WHY A NEW COLUMN AND NOT updated_at
--
-- The ticket referee is offered the 5 most recent candidate tickets for a conversation,
-- ordered by created_at. That bound is fine while tickets are rare and get closed. Under
-- the ticket-model redesign every customer query gets a LOGGED ticket, and nothing ever
-- closes those - nobody resolves "what is my card limit?". So five routine questions fill
-- all five slots and push a live dispute out of view: the follow-up "any update on my
-- dispute?" would arrive with its own ticket ABSENT from the candidate list, and fork a
-- duplicate. The symptom looks like an LLM accuracy problem; the cause is ORDER BY.
--
-- Ordering by "last touched" is the fix, but updated_at cannot supply it - two measured
-- reasons, both of which cost a wrong turn earlier in this redesign:
--
--   1. updated_at does not mean last touched. create_or_get_ticket ends with
--      `if existing: return existing` - attaching a message to a ticket never calls
--      update_ticket. Proven on ticket 7f590b: updated_at 13:11:19, with a message
--      attached at 13:11:49 that did not move it. The field tracks ADMINISTRATIVE
--      changes (created, scope refined, referee attached, status updated).
--
--   2. Repurposing it would corrupt analytics by an order of magnitude. Three readers
--      treat updated_at as the close time (average resolution, per-team average,
--      closed-per-day). Measured on live data, average resolution time would report
--      18.3 minutes instead of 394.2 - a 21x change on a headline demo metric.
--
-- So: a separate field. updated_at keeps its meaning, analytics is untouched, and the
-- referee gets a column that says what it actually needs.
--
-- NULL is the correct default for existing rows, not created_at. NULL means "no message
-- has attached since this column existed", and readers use
-- COALESCE(last_activity_at, created_at) so an untouched ticket keeps exactly its old
-- ordering. Backfilling created_at would assert an activity that never happened.

ALTER TABLE tickets ADD COLUMN last_activity_at TEXT;

-- Ordering is per-conversation and reads both columns, so index the pair.
CREATE INDEX IF NOT EXISTS idx_tickets_conv_last_activity
    ON tickets(conversation_id, last_activity_at);
