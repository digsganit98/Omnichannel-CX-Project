-- 019: ownership and lifecycle for the Service Desk.
--
-- WHY THESE COLUMNS AND NOT NEW STATUS VALUES
--
-- The Service Desk needs to say four things a ticket cannot say today: who owns it, when
-- we first answered, whether we owe the customer a follow-up, and who closed it and why.
--
-- The obvious design was new TicketStatus values ('awaiting_customer', 'promised'). That
-- was measured and rejected: status is ENUMERATED at 11 sites across Python and JS -
-- _SERVICEABLE_SQL and three more queries in analytics_service/aggregator.py, the Neo4j
-- open-case query, the Jira alias map in crm_service/client.py, isServiceable() in
-- app.js and four graph/lineage branches beside it. A new value is absent from every one
-- of those lists, so a ticket carrying it would silently vanish from analytics, the
-- graph, lineage and the inbox while still existing in the table. That is the failure
-- recorded in the session log for Fix 149 (a change to what a structure carries turned
-- three escalation gates into constants), and the cost of re-learning it here is a demo
-- where tickets disappear.
--
-- Timestamps have no such problem. Nothing enumerates them, so "we have replied" and "we
-- owe a follow-up" become derivable facts rather than states that must be added to
-- eleven lists. The status vocabulary is untouched: logged / open / in_progress / closed.
-- in_progress already exists in the enum and has never been written; an agent picking a
-- ticket up is exactly what it was meant for.
--
-- NULL is the correct default for every column here. A NULL first_response_at means "not
-- answered yet", which is true of every existing row - backfilling created_at would
-- assert a reply that never happened, the same reasoning 018 used for last_activity_at.

ALTER TABLE tickets ADD COLUMN assigned_to TEXT;
ALTER TABLE tickets ADD COLUMN assigned_at TEXT;
ALTER TABLE tickets ADD COLUMN first_response_at TEXT;
ALTER TABLE tickets ADD COLUMN follow_up_due_at TEXT;
ALTER TABLE tickets ADD COLUMN closed_by TEXT;
ALTER TABLE tickets ADD COLUMN closure_reason TEXT;

-- admin_users gains the two facts routing needs. No role column: everyone who reaches
-- the console sees the same board, so a permission split would separate nobody from
-- nobody. team is NULL-able because an account need not belong to one.
ALTER TABLE admin_users ADD COLUMN team TEXT;
ALTER TABLE admin_users ADD COLUMN capacity INTEGER NOT NULL DEFAULT 8;

-- "what does this person currently owe" is the board's hottest query.
CREATE INDEX IF NOT EXISTS idx_tickets_assigned
    ON tickets(assigned_to, status);

-- Unassigned serviceable work - the "needs triage" list.
CREATE INDEX IF NOT EXISTS idx_tickets_unassigned
    ON tickets(status, assigned_to);
