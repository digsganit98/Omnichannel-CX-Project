# Session Changes Log

Running log of changes made to fix portal / BFSI-data / identity issues, starting from the
`digvijay-work-branch` code (local working branch: `Sayantini-phase2-ui-changes`).

**Keep this document updated** as further changes are made in ongoing sessions.

---

## Summary (one line per change)

Keep this list updated: add a one-sentence entry here for every fix/change made in any session.

Terse one-liners only; full detail lives in the per-fix sections below.

- **Fix 1 — Portal identity resolution:** Match portal signups to the real seeded BFSI customer by email/phone (no phantom/duplicate).
- **Fix 2 — Chat bubble sides:** Portal chat — customer message on the right, AI reply on the left.
- **Fix 3 — Portal section order + heading:** Reorder ticket panels; "User Tickets" → "Support Center".
- **Fix 4 — Card/account/FD routing:** Route card/account/FD lookups through `neo4j_answer` (added intents to `TRANSACTIONAL_INTENTS`).
- **Fix 5 — Email corruption + trusted-context gap:** Stop writing `web_session:` into email; put card/account/FD data in the trusted context slot (real ₹10,65,000).
- **Fix 6 — Inbox real name:** Show the real Neo4j customer name in the inbox, not the portal username.
- **Fix 7 — No fake data for unknown signups:** Unmatched signups create no Neo4j node/synthetic data; validation rejects them correctly.
- **Fix 8 — No false escalation promise:** Prompt tweak so replies don't claim escalation when no ticket is created.
- **Fix 9 — Portal chat = web-chat turns only:** Portal history scoped to `channel="web_chat"` (was replaying WhatsApp/email).
- **Fix 10 — Human-in-the-loop reply drafts:** Ticket-worthy replies are held as an editable draft (customer gets a holding message); admin edits + sends manually.
- **Fix 11 — NBA not lingering on resolved tickets:** Agent-assist drops recommendations for resolved/closed tickets (read filter + rule allow-list).
- **Fix 12 — Removed portal "Latest submission" panel:** Redundant + exposed internal fields; deleted the section and dead code.
- **Fix 13 — Portal layout: wider chat + inline-expand tickets:** Chat column widened; ticket rows expand/collapse in place.
- **Fix 14 — One reply surface on held conversations:** Hide the old (stub) compose box while a draft card is shown.
- **Fix 15 — Draft-card header readability:** White-on-amber header (was unreadable amber-on-amber).
- **Fix 16 — Manual email reply threads in Gmail:** Send with the original subject + Message-ID so the reply threads.
- **Fix 17 — Held drafts capture the inbound turn id:** Set `state.inbound_turn_id` (was never assigned) — makes Fix 16 actually work.
- **Fix 18 — Per-ticket resolution:** Removed conversation-level Resolve/Escalate; per-ticket Resolve; conversation-resolved is derived.
- **Fix 19 — Clickable Tickets-panel rows:** Click a ticket → jump to its turn (`goToConversation` exposed on `window`).
- **Fix 20 — Portal "My Tickets" = all tickets, all channels:** One row per ticket (open + closed), grouped, channel from `ticket.metadata.channel`.
- **Fix 21 — Per-ticket detail:** `GET /user/ticket-detail/{ticket_id}` returns that ticket's own message + reply (was the conversation's latest).
- **Fix 22 — Ticket detail in a modal:** Roomy modal (replaces the cramped/truncated inline expand).
- **Fix 23 — Portal ticket-row polish:** Green Resolved pill, per-channel colored pills, Created date; fixed a clip regression; internal panel scroll; removed the big heading; "Refresh tickets" → "Refresh".
- **Fix 24 — Foldable theme/sub-theme dividers in the admin conversation flow:** Group turns by theme (team an intent maps to) with a clickable, foldable header + turn count; lighter sub-theme markers when the intent shifts within a theme. Frontend-only, derived from existing `intent`.
- **Fix 24a — Divider no longer splits a single ticket:** Ticket-first grouping — turns sharing a `ticket_id` stay one unit (one theme, no divider inside); sub-theme markers only between unticketed turns.
- **Fix 24b — Sub-theme marker between tickets in a theme:** Within a theme group, a light sub-marker (labelled by the new ticket's intent) marks a transition to a *different* ticket, so "separate request, same theme" is visible without ever splitting one ticket.
- **Fix 24c — Spine-timeline conversation view (replaces 3-column flow):** Merge each request (a ticket's turns) into ONE spine node showing the customer message + final reply; demote the "Support Agent will help shortly" holding message. Kills duplicate reply rows + blank-column asymmetry. Theme header counts now read "N requests".
- **Fix 24d — Spine node polish (per user review):** "Customer Query" eyebrow above the message; header pill order = ticket → status → sentiment → channel; holding message shown as a quoted "Auto-sent: …" line (was a vague pill); smaller body text (query 11.5px / reply 11px).
- **Fix 24e — Intent shown once as node title + query styling:** Removed the between-node "INTENT · X" sub-theme marker (it duplicated the node title and was inconsistent — only fired between units). Intent now shown once as each node's title, prefixed with an "INTENT" badge in the theme colour. Customer query = "CUSTOMER QUERY" label inline (blue) + message in normal text colour. Auto-sent line 10→11px (matches reply).
- **Fix 24f — Foldable request nodes:** Each spine node collapses to header + customer query; clicking reveals the replies (Auto-sent line + AI Agent reply). Latest node open, rest collapsed on load; per-node fold state keyed by ticket/idx, preserved across the poll. Chevron on the header; nodes with no replies aren't clickable.
- **Fix 24g — Query disappeared + per-exchange sub-boxes (bug):** `buildUnits` walked a ticket's turns newest-first but treated them oldest-first, so it showed the customer's LAST line as the query and an earlier reply as the answer (the original "Please transfer…" query vanished). Now walks chronologically, and a multi-turn ticket renders each customer message + its reply as its own exchange sub-box inside the one node (ticket never split).
- **Fix 24h — Timestamps + all-queries-when-collapsed:** Per-exchange timestamp on each sub-box; node header shows latest-activity time so it's visible even when collapsed. Collapsed view now shows ALL customer queries in the ticket (only the replies fold) — earlier it showed just the first query (an unrequested assumption, corrected).
- **Fix 24i — "Collapse all" toggle:** Button at the far-right end of the View/channel-filter bar collapses EVERYTHING — every theme section AND every request node; flips to "Expand all" once all are collapsed (reopens both). Uses `collapsedThemes` + `collapsedNodes` state (persists across the poll, per conversation).
- **Fix 24j — Removed redundant node-header timestamp:** Each query already shows its own timestamp (visible collapsed + expanded), so the extra `.spine-head-time` under the header was dropped.
- **Fix 24k — All nodes collapsed by default:** On first open of a conversation, every request node now seeds collapsed (was: latest node open, rest collapsed). Themes still default to latest-open; manual fold choices still preserved per conversation.
- **Fix 25 — Portal ticket modal shows full exchanges:** `/user/ticket-detail` now returns every customer-message→reply exchange for a ticket (was one message + one reply), rendered as sub-boxes with per-exchange timestamps; matched admin fonts.
- **Fix 26 — Agent Profile Snapshot redesign:** Replaced hardcoded Loans/Claims + ad-hoc churn heuristic with agent-useful tiles — **Tenure, Segment, Upcoming event** — plus per-item tooltips. `/graph` now returns `segment`, `contacts_30d`, and the most-urgent `upcoming_event` (card due/dpd, FD maturity, policy premium; 90-day window, overdue-first).
- **Fix 27 — Attrition risk (rule-based):** New `services/attrition_service` scorer → Low/Med/High + reasons over BFSI + conversation signs (dpd, below-min balance, thin relationship, tenure, fraud flag, bad mood, stuck ticket, repeat contact, exit-language override). Shown as a full-width band above the tiles. Named "Attrition risk" not "Churn" (heuristic, no outcome labels). See [[attrition-risk-rules]] memory.
- **Fix 28 — Right-panel + compose cleanups:** Sentiment label+value on one line with "(last N messages)"; consistent 12px value sizing (incl. attrition as plain text, not a pill); removed redundant channel chips from the customer header; removed the "Contacts · 30d" tile (kept in attrition calc); removed the non-functional "Reply via" channel buttons (send is a simulation stub); Detected intents shows top 4.

Also: corrected an earlier wrong claim about L1/L2/L3 ticketing (see "Correction" — level is decided per-query by an LLM, not fixed per intent).

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

---

## Session 2 — 2026-07-15

Branch: `Sayantini-phase2-ui-changes`.

### Fix 24 — Foldable theme / sub-theme dividers in the admin conversation flow
**Goal:** In the admin inbox, a customer's turns were rendered as one continuous stack even
when the topic changed (card question → loan question → …). Separate the conversation visually
by **theme** and **sub-theme**, and let the agent fold each theme group.

**What theme/sub-theme map to (no new data model):** there is no `theme` field in the schema —
the only per-turn classification is `intent`. So **Theme = the team the intent maps to**
(mirrors `INTENT_TO_TEAM` in `shared/constants/intents.py`, e.g. `card_management → Card
Services`, `loan_* → Loans`) and **Sub-theme = the intent itself**. Both are derived on the
frontend from the `intent` already on each turn. **Frontend-only — no backend/schema/migration/reseed.**

**Behavior (ticket-first, then theme — see Fix 24a for the rule that ships):**
- Turns (newest-first) are split into contiguous **theme groups** at each real boundary.
- Each group has a **foldable header** (`role="button"`, `tabindex`, `aria-expanded`,
  Enter/Space to toggle): a rotating chevron, a colored theme label, and a **turn count**.
- **Default fold state:** on a conversation's first render, every group is collapsed **except
  the latest** (group index 0). Seeded once per conversation (`state.themeSeeded`) so the ~3s
  inbox poll re-render never re-collapses a group the agent opened.
- Fold state is keyed `"<conversation_id>:<groupIndex>"` in `state.collapsedThemes`.
- If navigating to a ticket (`highlightTicketId`), the group containing that turn is force-opened
  so the highlighted turn isn't hidden.

**Files changed (frontend only):**
- `apps/admin-ui/app.js` — added `INTENT_TO_TEAM` / `TEAM_LABEL` / `THEME_COLOR` + `themeOf()`
  near the `CH` constant; added `collapsedThemes` / `themeSeeded` to `state`; restructured
  `renderCentre`'s per-step render into a `renderStep()` helper wrapped by a theme-group loop
  that builds foldable headers + sub-theme markers.
- `apps/admin-ui/style.css` — added `.flow-theme-group` / `.flow-theme-divider` (interactive:
  hover, focus-visible ring, chevron rotation, `.collapsed` hides the body) and
  `.flow-subtheme-divider`, all via existing theme tokens (light/dark safe).
- `docs/theme-divider-plan.html` — a visual before/after plan was saved here, then **deleted**
  once the design was replaced by the spine timeline (Fix 24c); the divider-only mock no longer
  matched the code. Design history lives in this log.

### Fix 24a — Divider no longer splits a single ticket / single request
**Problem (found in live testing):** dividers fired *inside* one ticket. Two causes, both
verified against real turn data (`conv_f0f35fa4190e`):
1. One customer message often produces **two outbound turns** sharing one `ticket_id` (a
   "Support Agent will help…" holding turn that carries the intent, then a full reply with
   `intent = (none)`). The pairing made these separate steps, and a **sub-theme marker** fired
   between an intent-carrying step and its own follow-up.
2. Within a ticket the small-LLM intent can flip (e.g. a KYC message mislabelled `fraud_report`,
   or `transaction_dispute` vs `fraud_report` on the same escalation), so two turns of the **same
   ticket** mapped to intents that produced a **theme divider** mid-ticket.

**Fix (ticket-first grouping):** a `ticket_id` is now treated as one unit.
- Each `ticket_id` takes a **single theme** (the first themed intent seen for that ticket), so an
  intent flip inside a ticket can't change its theme.
- A new group starts only when the theme changes **and** the step doesn't share a ticket with the
  previous step (`sameTicket` suppresses the boundary).
- The **sub-theme marker** now fires **only between unticketed turns** whose intent shifts; it
  never marks a shift into/out of/within a ticket.

**Verified (simulation on the real 33-turn thread):** 20 steps → **6 clean groups**; the four
fraud/dispute tickets all sit in **one** Fraud & Disputes group; **no `ticket_id` appears in more
than one group**. Served JS re-checked in Chrome (parses; no SyntaxError).

### Fix 24b — Sub-theme marker between different tickets in a theme
**Why:** after 24a the sub-theme marker only fired on unticketed same-theme intent shifts, which
are rare in this data (most classified turns carry a ticket), so it was seldom visible. Per user
choice, the marker now surfaces "separate request, same theme".

**Rule:** within a theme group the sub-theme marker fires when (a) the step enters a **different
ticket** than the previous step (labelled by the new ticket's first intent), or (b) an
**unticketed** intent shift between two ticket-less turns. It still **never** fires inside a
ticket, so a single ticket is never split.

**Files:** `apps/admin-ui/app.js` — added a `ticketIntent` map (first intent per ticket) and
reworked the sub-theme block to the two-case rule above.

**Verified (simulation on the real thread):** the Fraud & Disputes group (4 tickets, 12 steps)
now shows **3 sub-markers** — one at each ticket→ticket transition (`fraud report`,
`fraud report`, `transaction dispute`) — and **0 markers inside any ticket** (incl. the ticket
whose intent flips KYC↔fraud). Served JS re-checked in Chrome (parses; no SyntaxError).

### Fix 24c — Spine-timeline conversation view (replaces the 3-column flow-step grid)
**Why:** even with the dividers, the conversation still looked "weird". Root cause (verified in
the data): each ticketed request produces **two outbound turns** — a `HOLDING_MESSAGE`
("Support Agent will help you with this shortly …", see
`services/orchestration_service/graph.py`) followed by the real reply — so every request rendered
as duplicate reply rows, and outbound-only turns left the left "Customer Query" column blank
(lopsided rows + floating center node). The heavy 3-column node grid amplified it.

**Design chosen (from a 4-option mock the user compared):** **Spine timeline** — a vertical
thread with a node dot per request.

**What it does:**
- **Merge each request into one unit** (`buildUnits`): consecutive items sharing a `ticket_id`
  collapse into one node; unticketed items are their own unit. Each unit shows the customer's
  opening message + the **final substantive reply**.
- **Demote the holding message** (not hidden): if a request's reply(ies) included the holding
  stub, show a small **"auto-ack sent"** pill on the reply; the substantive "Dear …" answer is
  the reply text. `isHolding()` matches the `HOLDING_MESSAGE` prefix.
- **Spine layout** (`renderUnit`): node dot (channel-coloured; blue ring on the latest) + a card
  with intent title + ticket + channel + emotion + status header, the customer message, and the
  AI reply below. Removes the blank-column asymmetry entirely.
- Theme header counts now read **"N requests"** (units), not raw turns.
- Sub-theme markers and fold/seed/highlight behaviour from 24/24a/24b carry over, now operating
  between **units**.

**Files:** `apps/admin-ui/app.js` — replaced `renderStep` (3-col) with `buildUnits` + `renderUnit`
(spine); body loop renders units; header count = request count. `apps/admin-ui/style.css` — added
`.spine` / `.spine-node` / `.spine-card` / `.spine-cust` / `.spine-reply` / `.spine-ack` etc. (the
old `.flow-step`/`.flow-node`/`.flow-query-card`/`.flow-reply-card` rules are now unused by the
conversation view but left in place).

**Verified (simulation on the real 33-turn thread):** Fraud & Disputes **12 steps → 4 request
nodes** (one per ticket); each unit merges to the real "Dear Sayantini…" reply; the
KYC-mislabelled ticket is one node, not split. Served JS + CSS re-checked in Chrome
(parses; no SyntaxError). **Final DOM click-through in a browser still pending** (no automation
driver installed here).

### Fix 24d — Spine node polish (per user review of the first spine build)
Six review points addressed in `renderUnit` + spine CSS:
1. **"Customer Query" eyebrow** (`.spine-cust-lbl`, blue) above the customer message.
2. **"auto-ack sent" was unclear** → the holding message is now shown as its own small quoted
   line, `↳ Auto-sent: "Support Agent will help you with this shortly …"` (`.spine-holding`),
   above the real reply. `buildUnits` now captures `holdingText` (the actual sent text) separately
   from `finalReply` (the substantive answer). If only a holding msg exists so far → "Awaiting
   agent reply…".
3. **Sub-theme name source = the intent** → marker now renders an **"Intent"** badge (in the
   sub-theme colour) followed by the intent name (`.subm-kind` / `.subm-name`).
4. **Header pill order** = ticket → status (active/resolved) → sentiment (positive/frustrated) →
   channel (title stays the heading, "Latest" stays last).
5. **Body font sizes reduced:** customer query 12→**11.5px**, AI reply 12→**11px** (subject 11px).
6. Answered #6 directly: the holding message never left the data (still a real outbound turn); it
   is now surfaced as the quoted "Auto-sent" line instead of a duplicate reply row.

Served JS + CSS re-checked in Chrome (parses). `buildUnits` re-simulated on the real thread: all
4 fraud units capture BOTH the holding text and the real "Dear Sayantini…" reply.

**Known/open:**
- Intent classification by the small LLM is non-deterministic; ticket-first grouping masks the
  worst effects (same-ticket turns stay together) but an unticketed mislabel could still nudge a
  boundary. Cosmetic only — never affects how turns are stored or resolved.
- Node not available in this environment, so `app.js` was verified via Chrome parse-check +
  Python simulation of the grouping against live data; final DOM click-through pending in browser.

---

## Session 3 — 2026-07-15

Branch: `Sayantini-phase2-ui-changes`. Agent-facing customer intelligence + portal ticket detail.

### Fix 25 — Portal ticket modal: full per-exchange history
**Problem:** the portal ticket-detail modal showed one "Your message" + one "Latest response",
so a multi-turn ticket lost its later queries (verified: the fund-transfer ticket's "okay,
close it" turn and its reply were dropped).
**Cause:** `/user/ticket-detail` returned the ticket's stored description (first message) +
`get_ticket_reply` (one reply) — it never read the ticket's turns.
**Fix:** added `repository.list_conversation_turns`; `_build_ticket_exchanges` in `user_portal.py`
reconstructs each customer-message→reply exchange (only outbound turns carry `ticket_id`, so an
inbound belongs to the ticket when the next outbound does). Endpoint returns an `exchanges` list
(kept `message`/`latest_response` for compat). `openTicketModal` renders each as a sub-box with a
per-exchange timestamp; fonts matched to the admin view.
**Verified:** end-to-end HTTP test → 2 correct exchanges; portal tests 12/12.

### Fix 26 — Agent Profile Snapshot redesign
Old tiles were Tenure / Churn(heuristic) / Loans / Claims — loans/claims were hardcoded counts
(not data-driven) that don't help an agent act. Reframed the panel around agent use: **Tenure,
Segment, Upcoming event** (3 tiles; Upcoming event full-width). Each has a native-tooltip
explaining what it shows + the rule.
- `/admin/customers/{id}/graph` extended: `segment` (Neo4j, was fetched-unused), `contacts_30d`
  (`repository.count_recent_inbound`), and `upcoming_event` (`_upcoming_event`): most-urgent
  product event across card `payment_due_date`+`dpd`, FD `maturity_date`, policy `next_premium_due`;
  **overdue-first, then soonest; 90-day window** (drops stale years-old FD maturities).
- Two bugs found+fixed during verification: stale FD events flooding the tile (added the window);
  past due-date with dpd=0 mislabelled not-overdue (derive overdue from `days < 0`).

### Fix 27 — Attrition risk (rule-based scorer)
Replaced the ungrounded frontend churn heuristic with `services/attrition_service/scorer.py`.
Named **Attrition risk**, not Churn: no historical outcome labels exist, so it is a transparent
heuristic, never a prediction. Scope = conversation + BFSI data.
- **Rules (v2):** override→High on exit-language; strong signs = dpd≥30, bad mood (≥40% high-urgency
  turns), stuck ticket (open past SLA / >3d no-SLA); weak signs = dpd 1–29, below-min balance
  (`avg_monthly_balance < min_balance_required`, a proxy — no balance history exists),
  fraud/chargeback flag, thin relationship (≤1 product type), new customer (<6mo), ≥3 contacts/30d.
  Banding: exit→High; ≥2 strong→High; 1 strong or ≥3 weak→Medium; else Low. Output = band + top-2
  reasons.
- Endpoint gathers the customer's cards/accounts/tickets/turns (`repository.list_customer_turns`)
  and returns `attrition`. UI shows a full-width band above the tiles (High=red/Med=amber/Low=green,
  plain text). Rules also captured in the `attrition-risk-rules` auto-memory.
- **Verified:** 12 isolated rule/boundary unit tests pass (every sign, band cutoff, override);
  end-to-end via endpoint gives sensible bands+reasons for all real customers.

### Fix 28 — Right-panel + compose cleanups (per user review)
- Sentiment: label+value on one line with "(last N messages)"; removed the separate trend line.
- Consistent value sizing at 12px across the panel (incl. the attrition band, now plain coloured
  text instead of a pill; "Frustrated" reduced 17→12px).
- Removed the redundant channel chips from the customer header (channel already shown per-turn and in
  the View bar); removed the "Contacts · 30d" tile (still computed for the attrition calc).
- Removed the non-functional "Reply via" channel buttons — they had no handler and `doSend` is a
  simulation stub; the real reply path is the human-in-the-loop draft cards. Kept the reply box.
- Detected intents now shows top 4 (was 3).

### Infra / verification notes
- API code is baked into the image (only `apps/admin-ui` is bind-mounted), so backend changes this
  session required rebuilding + restarting the `api` container. Frontend changes are live via mount.
- Frontend verified by Chrome parse-check + data simulation; visual rendering confirmed by the user
  via screenshots. Backend verified via TestClient HTTP calls + isolated unit tests against real data.
