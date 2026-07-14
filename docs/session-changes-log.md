# Session Changes Log

Running log of changes made to fix portal / BFSI-data / identity issues, starting from the
`digvijay-work-branch` code (local working branch: `Sayantini-phase2-ui-changes`).

**Keep this document updated** as further changes are made in ongoing sessions.

---

## Summary (one line per change)

Keep this list updated: add a one-sentence entry here for every fix/change made in any session.

- **Fix 1 — Portal identity resolution:** Match portal signups to the real seeded BFSI customer by email/phone before minting a hash id, so no phantom/duplicate customer is created.
- **Fix 2 — Chat bubble sides:** In the customer portal chat, put the customer's own message on the right and the AI reply on the left.
- **Fix 3 — Portal section order + heading:** Swap "My submitted tickets"/"Latest submission" and rename the heading "User Tickets" → "Support Center".
- **Fix 4 — Card/account/FD data routing:** Add `card_management` + `account_balance_inquiry` to `TRANSACTIONAL_INTENTS` and handle credit-card/account/FD lookups in `neo4j_answer`.
- **Fix 5 — Email corruption + trusted-context gap:** Stop writing the `web_session:` string into the customer email, and surface card/account/FD data in the trusted "Customer account context" slot so real data is returned (₹10,65,000, not fake ₹2,00,000).
- **Fix 6 — Inbox real name:** Propagate the real Neo4j customer name into the SQLite `display_name` so the inbox shows "Sayantini Sarkar" instead of the portal username.
- **Fix 7 — No fake data for unknown signups:** New signups with no seeded match create no Neo4j node/synthetic data, so the existing `CustomerValidationAgent` correctly rejects their account-specific queries.
- **Fix 8 — No false escalation promise:** Soften the LLM prompt so replies don't claim "I need to escalate" when no ticket is actually created (prompt-only; non-deterministic limitation noted).
- **Fix 9 — Portal chat shows web-chat turns only:** The customer portal chat window was replaying the customer's WhatsApp/email turns (history was keyed by `customer_id` with no channel filter). Now the portal history is scoped to `channel="web_chat"`; the admin inbox's unified cross-channel view and the pipeline context are unchanged.
- **Fix 12 — Removed the portal "Latest submission" panel:** It duplicated the chat window + My Tickets and exposed internal fields (Conversation ID, Channel) plus an often-empty "Phone/Email used". Removed the section + `showUserLatest` and all its callers entirely (no dead code). Portal-only, no rebuild (bind-mounted UI).
- **Fix 23 — Portal ticket rows: green Resolved pill, per-channel colored pills, Created date, misc UI polish:** Resolved status pill is green (was amber for all); channel pills use the admin app's per-channel colors (WhatsApp green / Email blue / Web Chat purple) via `chMeta`; each row shows "Created: …". Also fixed a clipping regression (removed a leftover `overflow:hidden` + added `flex-shrink:0` so the Created line isn't cut off), the portal panels scroll internally (no page scroll), removed the oversized "Support Center" heading (kept eyebrow+subtitle), and renamed the ticket "Refresh tickets" button to "Refresh".
- **Fix 22 — Ticket detail opens in a modal (was a cramped/truncated inline expand):** Clicking a portal ticket now opens a roomy modal (scrollable body, Esc/click-out/✕ to close) showing that ticket's own message + real reply. Replaces the inline expand that clipped long responses.
- **Fix 21 — Ticket detail is per-ticket, not per-conversation:** Expanding any ticket showed the conversation's latest message (all tickets share one conversation). New `GET /user/ticket-detail/{ticket_id}` + `repository.get_ticket_reply` return the ticket's own message (from its description) and its real reply (latest non-holding outbound turn tagged with that ticket_id), with an ownership check.
- **Fix 20 — Customer portal "My submitted tickets" shows ALL tickets across channels (open + closed):** Was showing one collapsed row per conversation (so effectively 1 ticket, and its channel was mislabeled from the latest inbound turn). Now `list_user_tickets` returns one row per ticket the user owns, across all channels, sorted open-group-first then newest; channel is read from `ticket.metadata.channel` (the tickets table has no channel column). New `_ticket_summary` helper. Frontend groups rows into Open/Resolved sections with channel pills (`userChannelMeta`). Honors the "track requests via WhatsApp and email" subtitle. Updated `test_user_ticket_list_is_scoped_to_portal_user` to the new per-ticket shape (kept the ownership-scoping assertion). Backend rebuilt; 12/12 portal tests pass.
- **Fix 19 — Tickets panel rows are clickable → jump to that ticket's turn:** Each ticket in the conversation Tickets panel now navigates to that ticket's turn (reuses `goToConversation(conversationId, ticketId)` highlight/scroll from the Tickets page). The per-ticket "Resolve ticket" button uses `event.stopPropagation()` so it doesn't also navigate. NOTE: `goToConversation` had to be exposed on `window` (`window.goToConversation = ...`) — the file is wrapped in an IIFE, so inline `onclick=` (global scope) couldn't reach a plain local function; that's why the first attempt silently did nothing. Admin UI only.
- **Fix 18 — Per-ticket resolution (conversation-level Resolve/Escalate removed):** With multiple open tickets on one conversation, the conversation-level "Resolve" closed only the newest ticket but marked the whole conversation resolved (stranding the rest + disabling the buttons); "Escalate" was a non-functional UI stub. Removed both conversation-level buttons; added a per-ticket "Resolve ticket" button in the Tickets panel (uses existing `PATCH /admin/tickets/{id}/status`); conversation "resolved" is now derived from having no open tickets left; removed the 4-ticket display cap so all tickets show. Admin UI only, no backend change, no rebuild.
- **Fix 17 — Held drafts now capture the inbound turn id (makes Fix 16 actually work):** Root cause of the manual email reply still not threading: `state.inbound_turn_id` was never assigned in the pipeline, so every held draft stored `inbound_turn_id=None` and Fix 16 had nothing to look up. Added the missing `state.inbound_turn_id = inbound_turn["turn_id"]` after the inbound turn is created. (Pre-existing gap — the field was declared and consumed at graph.py:423/612 but never set.) NOTE: drafts created before this fix still have None and won't thread — must test with a fresh held email.
- **Fix 16 — Manual email reply threads into the original Gmail conversation:** The agent's manually-sent draft (2nd email) arrived as a *separate* mail because the send route passed no subject and used the internal turn id as the reply reference. Now it looks up the original inbound email turn (new `repository.get_turn`) and sends with the real subject (`Re: <original>`) + the real Message-ID as In-Reply-To/References, so Gmail threads it. Non-email channels unaffected.
- **Fix 15 — Draft-card header readability:** the held-draft card header used amber-on-amber (low contrast, unreadable). Now white text on a solid amber bar, reason as a white pill, dark label text on the light body.
- **Fix 14 — One reply surface on held conversations:** On a held conversation the admin saw TWO send boxes — the real draft card and the old lower "Reply via" composer (a non-functional "simulation mode" stub). Now the lower compose box is hidden whenever a draft card is showing (`renderDraftCard` hides `compwrap`); after Send/Discard, `renderCentre` restores it. Portal/admin UI only, no rebuild.
- **Fix 13 — Portal layout: wider chat + expandable tickets:** Made the chat column wider than the tickets column (`1.35fr` vs `.9fr`, was `.9fr`/`1.1fr`). Ticket rows are now inline expand/collapse: clicking a ticket expands it in place to show the full message + latest response (lazy-loaded from `/user/tickets/{id}`, cached), clicking again collapses. Replaced the now-dead `refreshUserTicket` (which fed the removed panel) with `toggleUserTicket`.
- **Fix 11 — Recommended Actions no longer linger on resolved tickets:** The agent-assist NBA panel kept showing an "Escalate to Senior" card after a ticket was resolved. Fix A (read filter): the `/next-best-actions` endpoint now drops pending recommendations tied to a resolved/closed ticket. Fix B (rule guard): the SLA-escalate rule uses a positive allow-list (only `open`/`in_progress`) so it never generates an escalate suggestion for a terminal ticket. Verified: near-due open ticket shows escalate → after resolve, 0 actions.
- **Fix 10 — Human-in-the-loop reply drafts:** When the review gate holds an AI reply (any query that requires a ticket — L2/L3/escalation), the customer now receives a holding message ("Support Agent will help you with this shortly ...") and the AI's real answer is stored as an editable draft. An admin sees a "Needs Review" badge/filter + an editable draft card in the inbox, corrects the text, and sends it manually (delivered + persisted as an outbound turn). The portal chat polls so web-chat customers see the agent's reply without refreshing.

Also this session: corrected an earlier wrong claim about L1/L2/L3 ticketing (see "Correction" section — the level is decided per-query by an LLM, not fixed per intent).

---

## Session 1 — 2026-07-14

Branch: `Sayantini-phase2-ui-changes` (created off `origin/digvijay-work-branch`).
Status at end of session: all changes applied and verified live; **not yet committed**.

### Context / how issues were found
Live-testing the customer portal (website chat) surfaced a chain of problems: wrong credit-card
data, duplicate customers, corrupted emails, UI issues, and unknown users receiving fake account
data. Each was diagnosed against the running stack (Neo4j + SQLite + API) before fixing.

### Files changed (7)
- `apps/admin-ui/index.html`
- `apps/admin-ui/app.js`
- `apps/api/routes/user_portal.py`
- `services/neo4j_service/queries.py`
- `services/orchestration_service/graph.py`
- `services/rag_service/groq_generator.py`
- `tests/test_user_portal.py`

---

### Fix 1 — Portal identity resolution (wrong data + duplicate customers)
**Problem:** Web-chat/portal signups created a phantom Neo4j customer (hash id `CUST######`)
with synthetic data instead of matching the real seeded BFSI customer (`CRN########`) by email.
Result: wrong card data and duplicate conversations for the same person.

**Fix:** `apps/api/routes/user_portal.py`
- Added `_resolve_graph_customer_id(user_id, email, phone)` — matches an existing BFSI customer
  by email/phone (via `get_customer_by_identifier`) before falling back to the hash id. Used in
  all metadata-building sites so GET (history) and POST (send) resolve to the SAME customer_id.
- `_upsert_customer_graph_user` matches existing customer first; when matched, refreshes runtime
  fields only and never seeds synthetic data over real data.

### Fix 2 — Chat bubble sides (customer portal)
**Problem:** In the portal chat, the customer's own message rendered on the left and the AI reply
on the right (inverted vs. expected).

**Fix:** `apps/admin-ui/app.js` — `renderPortalChatTurns` now maps the customer's message
(`inbound`) to the right bubble and the AI reply (`outbound`) to the left (inverted vs. admin inbox).

### Fix 3 — Portal section order + heading
**Fix:** `apps/admin-ui/index.html`
- Swapped "My submitted tickets" and "Latest submission" positions.
- Renamed the `<h1>` heading "User Tickets" → "Support Center".
- NOTE (not yet done): the ribbon nav still contains a leftover "User Tickets" label.

### Fix 4 — Card / account / FD data routing (`neo4j_answer`)
**Problem:** `neo4j_answer()` only handled loan/claim/policy intents. `card_management` and
`account_balance_inquiry` were missing from `TRANSACTIONAL_INTENTS`, so card/FD queries returned
no graph data and escalated — even though the data and query helpers existed.

**Fix:** `services/neo4j_service/queries.py`
- Added `card_management` + `account_balance_inquiry` to `TRANSACTIONAL_INTENTS`.
- Added handler branches in `neo4j_answer` for credit cards, accounts, and fixed deposits.

### Fix 5 — Email corruption + trusted-context gap (wrong ₹2,00,000, false escalation)
**Problem A:** The orchestration pipeline wrote `email = channel_identifier` for non-WhatsApp
channels. For web chat that identifier is `web_session:<user>`, which **overwrote the real
customer's email** and helped create a phantom node with a synthetic ₹2,00,000 card.
**Problem B:** Card/FD data reached the LLM only through the weaker "retrieved context" slot, not
the trusted "Customer account context" slot, so the LLM still hedged and escalated.

**Fix:**
- `services/orchestration_service/graph.py` — only write a real email (prefer `linked_email` /
  `portal_contact_identifier`; never the raw `web_session:` identifier).
- `apps/api/routes/user_portal.py` — web-chat metadata now includes `linked_email`.
- `services/neo4j_service/queries.py` — `get_customer_context_for_customer` now loads
  credit_cards/accounts/fixed_deposits (and `name`).
- `services/rag_service/groq_generator.py` — `_format_graph_context` now renders Credit Cards,
  Accounts, and Fixed Deposits so the data lands in the trusted "Customer account context" slot.

**Verified:** real card limit **₹10,65,000** returned; email no longer corrupted; no phantom node.

### Fix 6 — Inbox shows real customer name (not portal username)
**Problem:** Admin inbox showed the raw portal username (e.g. `sayantini_v2`) instead of the real
customer name, because the pipeline's name-propagation block skipped portal messages.

**Fix:** `services/orchestration_service/graph.py` — added a portal branch that pulls the real
name from Neo4j (`get_customer_by_id`) into the SQLite `display_name` (only overrides a
username-style/generic name). Verified: inbox now shows "Sayantini Sarkar".

### Fix 7 — New/unknown signups no longer get fake account data
**Problem:** Signups whose email matched no seeded BFSI customer had a phantom Neo4j customer +
synthetic records fabricated (on signup AND on every message), making them look "registered" and
bypassing the existing `CustomerValidationAgent` reject flow — so unknown users got fake
₹2,00,000 card data.

**Fix (uses existing validation logic rather than new code):**
- `apps/api/routes/user_portal.py` — `_upsert_customer_graph_user` returns `status:"unregistered"`
  and creates NO node / NO synthetic records when no real customer matches.
- `services/orchestration_service/graph.py` — pipeline skips all Neo4j customer/interaction writes
  (Phase 1 and Phase 2) for unmatched portal users, so nothing re-registers them. Non-portal
  (WhatsApp/email) paths unaffected.
- `tests/test_user_portal.py` — replaced the old synthetic-seeding test with two tests:
  `test_unknown_signup_creates_no_synthetic_neo4j_customer` and
  `test_matched_signup_refreshes_but_does_not_seed`.

**Verified:** unknown email → "We couldn't verify your account…" rejection; real email → real data;
0 phantom customers in Neo4j.

---

### Fix 8 — Reply no longer falsely promises escalation when no ticket is created
**Problem:** The LLM answer text could say "I need to escalate this to our support team" even when
the backend correctly resolved the query with NO ticket (e.g. an L1 FD/card lookup). The answer
text (generated at `resolve_query`) and the ticket decision (made later at `decide_ticket`) are
independent, and nothing reconciled them — so the customer was promised follow-up that never
happened.

**Fix (option B — prompt tweak only, per user's choice):**
- `services/rag_service/groq_generator.py` — replaced the rule
  *"If context is insufficient, say: 'I need to escalate this to our support team.'"* with a rule
  that tells the model to answer what it can and mention a specialist can help further, and to
  NEVER state/imply an escalation or ticket has happened (the system decides that separately).

**Verified** (direct generator call with real FD context): the previously-escalating FD "next step"
query now answers with the real FD data and a natural next step, no false escalation promise.

**Known limitation:** LLM wording is non-deterministic, so this prompt-only fix reduces but does
not 100% guarantee the mismatch is gone. A deterministic post-process (strip the escalation
sentence when `ticket_decision.required is False`) was proposed but NOT implemented this round.

### Fix 9 — Portal chat window now shows web-chat turns only (not WhatsApp/email)
**Problem:** In the customer portal ("Support Center"), the website chat window replayed the
customer's WhatsApp and email messages too. Root cause: the portal history path
(`GET /user/chat/messages`) keys on `customer_id` — `get_or_create_conversation(customer_id)`
returns one conversation per customer (no channel column), and `list_recent_turns(conversation_id)`
returned every turn with no channel filter. So the unified cross-channel history rendered inside the
web-chat box.

**Fix (SQL-level channel filter, scoped to the portal — admin inbox/pipeline unchanged):**
- `services/persistence_service/repository.py` — `list_recent_turns` gained an optional
  `channel: str | None = None` param (defaults to current behavior; when set, adds
  `AND channel = ?` so the `LIMIT` applies to already-filtered rows — no truncation bug). The
  abstract stub signature was updated to match.
- `apps/api/routes/user_portal.py` — `get_user_chat_messages` now calls
  `list_recent_turns(..., channel="web_chat")`, so the portal chat shows only website-typed turns.
  WhatsApp/email turns remain in the DB and in the admin inbox's unified view; the cross-channel
  "connected account" story stays intact via the portal's My Tickets panel.

**Chosen over** a post-fetch Python filter in the endpoint, which would have filtered *after* the
DB `LIMIT 50` and could truncate web-chat turns behind older WhatsApp/email ones. Verified both
changed files byte-compile.

### Fix 10 — Human-in-the-loop reply drafts (escalation held for agent review)
**Goal:** For any query that requires a ticket (escalation / L2 / L3 / L1-via-intent-rule), do NOT
auto-send the AI's answer. Send the customer a holding message, and hold the AI answer as an
editable draft that a human agent reviews, corrects, and sends manually.

**The gate rule** (`services/workflow_service/review_gate.py`, new): `should_hold_for_review(ticket_decision, resolution)`
holds **iff `ticket_decision.required` is True**. That one boolean is already the single source of
truth for escalation (folds in L3, L2, and every L1 intent-rule escalation), so the hold decision
can never drift from the ticketing logic. The resolution level / ticket reason are read only to
build a friendly UI label ("Critical escalation (L3)", "Assisted resolution (L2)", ...). Low-confidence
was deliberately NOT added as a separate trigger: anchoring it to the existing code threshold (0.3)
made it fully redundant with the ticket path (Rule 8 already escalates below 0.3), and a meaningful
higher threshold would have been an ungrounded guess (user chose "escalation only").

**Files:**
- `services/workflow_service/review_gate.py` (new) — the pure rule + `ReviewGateResult`.
- `services/persistence_service/migrations/009_reply_drafts.sql` (new) — `reply_drafts` table
  (draft_text, hold_reason, reason_code, channel, channel_identifier, provider, inbound_turn_id,
  status pending→sent/discarded, sent_text, audit fields). Mirrors the agent_assist pattern.
- `services/persistence_service/repository.py` — `add_reply_draft` / `list_reply_drafts` /
  `get_reply_draft` / `update_reply_draft` (+ Protocol stubs).
- `services/orchestration_service/state.py` — added `held_for_review: bool` and `draft_id`.
- `services/orchestration_service/graph.py` — in `_generate_and_send_reply`, after the answer is
  composed and BEFORE sending: if the gate holds, store the AI answer as a draft, then REPLACE
  `state.answer` with the `HOLDING_MESSAGE` so the holding message is what actually gets delivered
  AND persisted as the outbound turn (existing persist path unchanged). Wrapped so a draft-write
  failure falls back to the original auto-send rather than dropping the reply. Emits a
  `reply_held_for_review` audit event.
- `shared/schemas/responses.py` — added `held_for_review` to `ChannelResponse` (surfaced by `_response`).
- `apps/api/routes/reply_drafts.py` (new) + registered in `apps/api/main.py` — admin routes
  (`require_admin_key`): `GET /admin/reply-drafts`, `POST /admin/reply-drafts/{id}/send`
  (delivers via `OutboundDeliveryService`, appends outbound turn, marks sent, audits),
  `POST /admin/reply-drafts/{id}/discard`.
- `apps/admin-ui/` — `loadPendingDrafts()` indexes pending drafts by conversation; a **"Needs
  Review"** ftag filter + amber count badge (separate from Urgent, which is unchanged); a queue-row
  amber dot; an editable **draft card** (`renderDraftCard`) above the compose box with Send/Discard
  (`sendDraft`/`discardDraft`). Plus a portal-chat poll (`bootUserPortal`, 8s) so web-chat customers
  see the agent's manually-sent reply without refreshing (cleared on logout).

**Verified live (rebuilt api image; migration 009 applied):**
- Escalation (L3 fraud): `held_for_review=True`, customer got the holding message, pending draft
  created with the AI's real answer + reason "Critical escalation (L3)" + channel/identifier/provider.
- Admin `POST …/send` with EDITED text: draft→sent, edited text delivered (`sent`), outbound turn
  persisted, pending count →0.
- Non-escalation (FAQ): `held_for_review=False`, real answer auto-sent, 0 drafts (unchanged behavior).
- Web-chat cycle: portal history (web_chat-only) shows the holding message, then after agent-send
  shows the agent's real reply — i.e. exactly what the portal poll renders. UI data endpoints all
  return the expected shapes; **DOM rendering not yet clicked through in a browser** (pending manual check).

**Known/open:**
- The gate holds on *ticket required*; low-confidence-without-ticket is intentionally NOT held.
- Admin-UI DOM not browser-verified this session (data paths were verified via the live API).
- Pre-existing CRM/JIRA 400 ("Specify a valid issue type") is unrelated to this change.

### Fix 11 — Recommended Actions (agent-assist NBA) no longer linger on resolved tickets
**Problem:** After a ticket was resolved (top "Resolve" button), the right-panel "Recommended
Actions" still showed an "Escalate to Senior — nearing SLA deadline" card. Root cause is a
*persistence* leak, not the rule: when the suggestion fires on an open ticket, a `pending` row is
written to `agent_assist_recommendations`; the GET `/admin/agent-assist/next-best-actions` endpoint
returns ALL pending rows, and nothing retires that row when the ticket resolves. (The generating
rule's guard was also narrow — it only excluded `resolved`, not `closed`.)

**Fix (A + B, no migration):**
- **A (read filter)** `apps/api/routes/agent_assist.py` — before returning, drop any pending
  recommendation whose `ticket_id` maps to a `resolved`/`closed` ticket (looked up via
  `get_ticket`, memoized). Conversation-level rows (no ticket_id) are unaffected.
- **B (rule guard)** `services/agent_assist_service/next_best_action.py` —
  `_rule_escalate_aging_high_priority` now uses a positive allow-list (`open`/`in_progress`) so an
  SLA-escalate is never generated for any terminal status.

**Verified live (rebuilt api):** the exact screenshot ticket `tkt_080526d25b41` (resolved) → 0
actions; a forced near-due OPEN critical ticket → shows escalate; after resolving it → 0 actions.
`tests/test_agent_assist.py` 18/18 pass.

**Not changed (design, flagged to user):** the top **Escalate** button's `execEscalate` is a UI-only
stub (appends a local "[Escalated…]" turn, no backend escalate action), and NBA **Approve** only
records a decision + audit event (does not perform the escalation). The Escalate-vs-Approve overlap
and whether Escalate should trigger a real action are left as open product decisions.

### Decisions deliberately NOT changed (by user's choice)
- **SQLite `cust_...` ID vs Neo4j `CRN...` ID in the inbox:** Separate id namespaces by design;
  left as-is.

### Correction to an earlier (incorrect) statement about ticketing
Earlier in the session it was stated that "card/FD queries create a ticket by design because they
are L2." **This was wrong.** Verified behavior (by calling `resolve_query_level` directly):

- The L1/L2/L3 resolution level is **NOT fixed per intent.** It is decided **per query** by
  `services/resolution_service/classifier.py::ResolutionDecisionEngine`:
  1. A deterministic high-risk keyword net (fraud/hacked/stolen/legal/ombudsman/…) forces **L3**
     before any LLM call.
  2. Otherwise it retrieves the top-k most similar labeled examples
     (`data/resolution_kb/resolution_examples.json`) and an LLM picks L1/L2/L3.
  3. Fallbacks: LLM failure → majority vote of retrieved examples; no examples → default **L2**.
- **What each level means** (`services/resolution_service/prompts.py`):
  - **L1 — auto-resolvable:** answerable from general KB or a simple data read.
  - **L2 — assisted resolution:** needs backend action / eligibility / a customer-specific change.
  - **L3 — critical escalation:** fraud, unauthorized txns, legal/regulatory risk.
- **How level drives ticketing** (`_escalation_reason`, "Rule 0", checked first):
  - **L3 → ticket** (`critical_escalation`); **L2 → ticket** (`assisted_resolution_required`);
  - **L1 → falls through** to intent rules (1–9); a plain answered lookup → **no ticket**.
- **Observed live levels:** "what is my credit card limit?" → **L1** (no ticket);
  "when is my FD maturity date?" → **L1** (no ticket);
  "I want to increase my credit card limit" → **L2** (ticket). So the earlier ticket on a card
  query was a run where the (non-deterministic) LLM classified it L2, not a fixed rule.

### Known / open items
- Ribbon nav still shows a leftover "User Tickets" label (only the `<h1>` was renamed).
- Small-LLM intent classification is non-deterministic (e.g. "credit card limit" sometimes
  classified as `general_inquiry`), which can affect whether card routing fires. Not fixed.
- 4 pre-existing test failures in `tests/test_phase1.py` (mock signature mismatches:
  `Recorder.send_text(reply_to_message_id=…)` and a `groq_generator` arg). **Pre-existing on
  digvijay-work-branch** — confirmed by stashing this session's changes; not caused by this work.

### Test status
- `tests/test_user_portal.py`: 12/12 pass.
- Full suite: 99 pass, 4 fail (the pre-existing failures noted above).

### Infra / data operations performed this session
- Created local branch `Sayantini-phase2-ui-changes` off `origin/digvijay-work-branch`.
- API is served on host port **8888** (→ container 8000). UI: `http://localhost:8888/admin-ui`.
- Several full-from-scratch rebuilds (wipe `neo4j-data` + `cx-data`, keep `ollama-data` /
  `huggingface-cache`) to reseed 5 real BFSI customers and clear test data.
- Final state: healthy stack, empty inbox (0 conversations), 5 real Neo4j customers, KB indexed.
- Changes are **uncommitted** at end of session.
