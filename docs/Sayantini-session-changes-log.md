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
- **Fix 29 — Removed "Detected intents" card:** Deleted the redundant right-panel card (intent is already shown per-request as each spine node's title, Fix 24e); frontend-only, dropped the unused `intents`/`uniqueIntents` derivation too.
- **Fix 30 — Two conversation views (Detailed + Lineage):** Added a `Detailed | Lineage` tab strip above the conversation. Detailed = the existing per-request view; Lineage = an at-a-glance overview of all past requests. Both render from the same `buildUnits` output. Clicking a Lineage row drills into Detailed for that request. Frontend-only (`state.convView` per conversation).
- **Fix 31 — Detailed = one request at a time:** Detailed now shows a single focused request (default = latest; a Lineage row / Tickets-panel jump sets the focus via `state.detailFocus`), under a static theme header. Validated focus falls back to latest if the stored request no longer exists.
- **Fix 32 — Removed per-node fold from Detailed:** Request nodes always show their replies (no chevron/click-to-expand); removed `collapsedNodes`/`nodeSeeded`. Theme-group folding kept; "Collapse all" now operates on themes (Lineage only).
- **Fix 33 — Detailed relaid out as stacked exchange rows:** Each customer→AI exchange in the focused request is its own 3-column row (Customer Query · ticket/channel/status/time · **AI Agent Reply**), oldest→newest. Fixes the multi-message ticket showing one query + one reply. Per-row sentiment pill (from that message's urgency) added to the middle column; middle column normalised to 10px, timestamp black. Intent label removed from the query box; auto-sent (holding) line shown inside the reply box.
- **Fix 34 — Groups keyed by raw intent (not team):** `themeOf` now groups by the raw `intent` (e.g. "Fraud Report" + "Transaction Dispute" as separate groups) instead of the team; colour still inherits from the intent's team. `ticket_resolution` system turns fold into their ticket's real intent (no bogus "Ticket Resolution" group; tickets never split). Verified on Fathima's real 32-turn thread (9 clean groups, no split).
- **Fix 35 — Lineage = timeline-strip rows:** Rewrote each Lineage row as a small left section (ticket-id + status) beside a mini timeline — one channel-coloured dot per exchange, oldest→newest, channel + time beneath — then a one-line "Opened with" opening-message snippet. Row's left border = theme colour (dots = channel). Fixes the first-Q/last-A mismatch. Removed the theme-header request count and the redundant "← Back to Lineage" button (the Lineage tab already switches views).
- **Fix 36 — Orange view tabs:** Active `Detailed`/`Lineage` tab styled orange (`#ea580c`) instead of blue.
- **Also (test data):** added **Group 4 — More scenarios** (#13–#22) to Fathima's section in `docs/hil-test-questions.md` — 10 grounded questions across claims / auto policy / disputed charge / loan penalty / exit-language, to give the Lineage/theme views more requests across more themes.
- **Fix 37 — Lineage ticket-id no longer clipped:** The fixed 104px meta column ellipsized the `TKT_…` id; changed the column to `auto` (hugs its content) and capped the pill at `max-width:150px` as an overflow safety net. CSS-only.
- **Fix 38 — Removed inbox "Urgent" triage:** Deleted the Urgent filter button, the red inbox nav badge, the "N urgent" queue chip (`#qcnt`), the urgent filter branch, and the urgent status dot/label; `urgencyToStatus` keeps its resolved/active/open logic. Frontend-only — backend urgency + ticket priority scoring untouched.
- **Fix 39 — Collapsed queue status label to Active/Resolved:** The row status pill dropped the "Open" case (unreachable — `conversations.status` is `NOT NULL DEFAULT 'active'`, so a conversation is never statusless); non-resolved now reads "Active". Deleted the now-unused `.dopn` dot rule. Display-only; no logic change.
- **Fix 40 — Detailed row left border = theme colour:** The Detailed `det-row` left border used the channel colour while its theme header (and the whole Lineage view) used the theme colour, so they didn't match. Switched `--det-clr` to the theme colour (`themeColor.t`), consistent with Lineage (Fix 35). Frontend-only.
- **Fix 41 — Unified status labels to Open / Resolved everywhere:** The app showed the same "not done" idea as four different words (conversation `active`/`Active`, ticket `open`/`Open`) across inbox/spine/lineage/right-panel/portal — confusing. Added a display-only `statusLabel()` mapping any raw status to just **Open** or **Resolved**, wrapped around the 6 display spans only. All logic/colours/branches keep reading the raw status untouched (verified). Supersedes Fix 39's "Active" label. Frontend-only; `in_progress` now displays as "Open".
- **Fix 42 — Cross-sell / Up-sell "Opportunities" (LLM-selected, code-guarded):** New opportunity engine (10 candidate rules + sentiment gate + LLM pitch + validation) → right-panel Opportunities card → Approve creates an editable offer draft → Send delivers to every push channel on record.
- **Fix 42a — Gates loosened to sentiment-only (user decisions):** Dropped the fraud/dpd, attrition-High, and open-ticket gates; only "latest message not negative" suppresses.
- **Fix 42b — Rules 8–10 added:** HNI-on-entry-card upgrade (dpd<30 guard), charge-waiver upgrade (≥2 unreversed charges), asked-about-product (recent intent → unheld product family).
- **Fix 42c — Removed the "Recommended actions" (NBA) card:** Redundant/decision-only; Opportunities is the one recommendation surface (backend NBA engine/endpoint kept; `_rule_cross_sell` deleted).
- **Fix 42d — Offer labelling in both conversation views:** Offer turns render as "Bank-initiated / Offer Message" rows (Detailed) and an amber Offer dot/pill (Lineage) instead of blank-query reply rows.
- **Fix 42e — Offer-glue grouping:** An offer turn never splits a ticket or starts its own request — question → offer → customer's reply-to-offer render as ONE request in Lineage + Detailed.
- **Fix 42f — Card heading "Opportunities" → "Suggested Offers":** Agent-facing wording (what the items ARE) over CRM jargon; empty/suppressed states now say "No offers right now". Display-only.
- **Also (test data):** Opportunity test scenarios added to `docs/hil-test-questions.md` (Sayantini Group 4, Fathima Group 5).
- **Fix 43 — Removed inbox-row status dot + label:** Dropped the redundant per-row "Open/Resolved" dot+text (state already encoded by the dimmed `done` row style); channel pill/stripe kept. Display-only.
- **Fix 44 — Snapshot tile "Upcoming event" → "Deadline":** More honest label — the tile's dominant state is an *overdue* (past) item, and all three sources are deadlines (card due, FD maturity, premium due). Display-only.
- **Fix 45 — Sentiment panel computes over the last 5 messages for real:** The "(last N messages)" caption was fake — counts/label ran over ALL inbound turns and the caption number was clamped per-verdict (3 when "Frustrated"). Now counts, bar, and label all derive from the true last-5 window; caption reports the actual window size.
- **Fix 46 — Sentiment + snapshot merged into one card:** Removed the "Profile snapshot" heading; the sentiment block and the attrition band/tiles now share one grey card, separated by a subtle top border. Display-only.
- **Fix 47 — Tickets card = open only, one-ticket height:** Right-panel card filters to open/in_progress tickets, header "Open Tickets (N)", scroll area capped at ~one open-ticket height (118px); card disappears when nothing is open. Resolved-ticket history stays visible in Lineage + portal My Tickets.
- **Fix 48 — Truthful Connectors page:** Gmail SMTP badge read a nonexistent `configured` field (endpoint returns `gmail_ready`) → always "Disconnected"; Jira CRM badge was a hardcoded literal, never calling the real `/admin/crm/status` (which reports configured:true). Both wired to their real statuses; the two email cards renamed "Email · Outbound (SMTP)" / "Email · Inbound (IMAP)" so the direction split is obvious.
- **Fix 48a — One Email card (merged), reordered:** The two email cards merged into a single "Email" card with per-pipe status rows (Inbound IMAP / Outbound SMTP — independent pipes that fail separately), keeping the stats + Poll-now; card badge = Connected/Partial/Disconnected. Card order now WhatsApp · Email · Call · Jira. Call kept (user choice).
- **Fix 49 — Removed the Tickets page:** Deleted the browse-all-tickets page + nav item + badge (no real user at scale; ticket lifecycle belongs to the Jira CRM the pipeline already syncs to; per-customer tickets live in the right-panel card, history in Lineage/portal, aggregates in Analytics). `_allTickets` cache kept (fed by `loadConversations`); `resolveTicket` rewired; fully revertible via git.
- **Fix 50 — Coloured right-panel card headings:** "Open Tickets (N)" heading amber, "Suggested Offers" purple (green then orange tried and rejected); Sentiment stays grey. Display-only.
- **Fix 51 — Ticket scope refinement (vague→specific, omnichannel):** A specific-scope follow-up ("...on my Mastercard") now refines the open `:other` dispute ticket instead of forking a duplicate; two different specific scopes (card vs upi) still get separate tickets. Backend; had been sitting uncommitted+unlogged from a prior manual test.
- **Fix 52 — Tier-4 LLM ticket referee (specific→vague, omnichannel):** When a message's scope label matches no open ticket (e.g. a vague "any update on my dispute?" arriving on another channel after the ticket was refined to `:card`), an LLM picks among code-vetted candidates (active, same intent, same conversation) or says NEW; any doubt/error/absent-LLM forks. Refining a scope now also appends the new details to the ticket description (was frozen at the vague opener). Fixes the live 23 Jul duplicate-ticket found during omnichannel demo testing.
- **Fix 53 — Offer send: dedupe push channels by destination:** The offer send loop messaged every whatsapp/email identifier, so a customer whose WhatsApp number was stored both bare (`7890864700`) and with the country code (`917890864700`) got the offer TWICE on WhatsApp. Added `_dedupe_push_identifiers` (normalize phone → strip non-digits + drop leading `91`; email → lowercased) so one message goes per real destination. Backend; symptom fix — the duplicate-identifier root (identity normalization on write) is a separate deferred item.
- **Fix 55 — Line breaks render in the Detailed conversation view:** `.det-q-text` / `.det-r-text` were missing `white-space:pre-wrap` (every other reply surface — spine, portal, modal — had it), so multi-line/multi-paragraph AI replies collapsed to one run-on block. Added `pre-wrap` to both; CSS-only, display-only.
- **Fix 56 — Graceful fallback when the LLM is unavailable (no more raw KB dump to the customer):** when generation returns `llm_used=False` (e.g. Groq 429/error), `rag_pipeline.answer` used to send the customer the raw top KB passage + an internal `Source: [1] InboxIQ_BFSI_KB.pdf:p1` citation. Replaced that branch with a clean holding message ("I'm having trouble accessing that information right now. Let me connect you with a support specialist…"); collapsed the two non-LLM branches into one and dropped the old `else`'s false "a support ticket has been created" promise. Backend; `retrieval_backend`/`citations` telemetry unchanged.
- **Fix 58 — WhatsApp offer failed to deliver (bare number → Meta 400):** an approved offer's WhatsApp turn 400'd (`#131030 Recipient phone number not in allowed list`) because the send loop used the customer's number stored **bare** (`7890864700`) — Meta needs the country code. Normal replies were unaffected (they mirror the sender's already-`91` inbound number). Added `_normalize_wa_recipient()` in [whatsapp_meta.py](../services/channel_adapter/whatsapp_meta.py) `send_outbound` (bare 10-digit → prepend `91`; already-prefixed/`+91` → digits; empty/None passthrough) so ALL WhatsApp sends use a Meta-valid format. Symptom fix (Level 1) — the duplicate-number ROW (identity normalization on write) is still the deferred root, same as Fix 53. Backend (api rebuilt); India-only `91` assumption (safe: all BFSI data Indian).
- **Fix 57 — Customer name now correct in admin inbox + all reply greetings:** `display_name` (which drives BOTH the admin inbox and the reply salutation) was being set to the customer's **email** for whatsapp/email channels — discarding the real `name` Neo4j already returned — so the admin showed an email-derived name and the email greeting reconstructed a mangled "Sayantini S 55" from `sayantini.s.55@…`; WhatsApp/web replies had **no** greeting at all. Now stores the real Neo4j `name` in `display_name` ([graph.py:257](../services/orchestration_service/graph.py)), and WhatsApp/web replies open with `Hi {name},` (falls back to "Customer" for unknowns) ([orchestration_agents.py:628](../services/agent_service/orchestration_agents.py)). Backend (api rebuilt); pre-existing test_phase1 failures unchanged (proven by stash-baseline).
- **Fix 54 — Connectors page: added Web Chat card + trimmed Email card:** Added a **Web Chat** connector card (customer-portal in-app chat, always Connected) as the 3rd card so order is WhatsApp · Email · Web Chat · Call · Jira — completing the channel story. Trimmed the Email card to just the badge + Inbound/Outbound Active rows (dropped Mailbox / Poll interval / Last poll / Emails processed + Poll-now button — demo-noisy, and "Last poll: Never / 0 processed" looked broken). Frontend-only; `triggerEmailInboxPoll` now dead (button gone) but left in place.
- **Merge — Analytics-page work (Digvijay `eb55195`) merged into this branch:** `--no-ff` merge (`f96cb5c`) folding Digvijay's analytics LLM-usage panel + migration `010` into `Sayantini-phase2-ui-changes`. Clean auto-merge, **zero conflicts** (verified via `merge-tree` dry run first); both branches' work verified coexisting; the 5 `test_phase1` failures proven **pre-existing** (identical on the pre-merge backup tree — 3 documented mock-signature + 2 Groq-key-blanked). Backup tag `backup-before-analytics-merge` → `a7da603`. api rebuilt so migration 010 applies.
- **Analytics page — whole-page creative redesign (frontend-only):** one shared `.kpi-tile` design system (gradient-accent tiles + top accent bar + icon + hover lift) applied to all 8 KPI tiles AND the LLM panel; bar charts → taller rounded gradient meters with row hover; sentiment bar → rounded gradient segments + keyed legend; Agent table → colour dots + tabular numerals; chart-card hover. No backend/data change.
- **Analytics — formula tooltips on every KPI card:** each KPI tile now shows its exact formula on hover (native `title` + a `?` affordance), across both the Customer Care set and the Solution Performance set.
- **Analytics — Solution Performance section rebuilt with practical, data-backed KPIs (backend + frontend):** replaced the broken/empty metrics (233% escalation bug, always-empty resolution-mix, single-day trend) with 4 KPIs that compute on real present-state data — **Escalation rate** (escalated tickets ÷ inbound customer queries = 7/18 = 38.9%; denominator is inbound turns so routine queries pull it down, never saturates), **Avg risk score** (AVG priority_score over open tickets = 60), **Critical load** (open critical tickets = 4), **Drafts handled** (reply_drafts sent = 14) — and 2 real charts: **Open tickets by risk band** + **Why tickets escalate**. New `/analytics/solution-performance` endpoint + `get_solution_performance` aggregator; api rebuilt.

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

---

## Session 4 — 2026-07-21

Branch: `Sayantini-phase2-ui-changes`. Right-panel trim (continuation of Fix 28's direction).

### Fix 29 — Removed the "Detected intents" card
**Why:** the right-panel "Detected intents" card (Profile snapshot area) listed up to 4 deduped
intent pills for the conversation. It was redundant: since Fix 24e each spine node in the main
conversation view already shows its intent as the node title (with an "INTENT" badge), in context
and per-request. The card flattened that away (no counts, no order, no link to which request), so
it told the agent less than the timeline already does while taking right-panel space next to the
more actionable tiles (Attrition risk, Tenure, Segment, Upcoming event). Fits the Fix 28 cleanup.
**Fix (frontend-only, admin-only):** `apps/admin-ui/app.js` — deleted the `Detected intents`
`rpcard` block from the `rpbody` innerHTML, and removed the now-unused `intents` / `uniqueIntents`
derivation (nothing else referenced them). No backend/schema change; live via the bind mount.
**Verified:** grep confirms `uniqueIntents` and the "Detected intents" string are fully gone with
no remaining references. No local `node` to run `--check`; parse to be confirmed on next UI load
(prior sessions used a Chrome parse-check).

### Conversation-view redesign (Fix 30–36) — 2026-07-21
All frontend-only (`apps/admin-ui/app.js` + `style.css` + asset-version bumps in `index.html`);
live via the bind mount, no backend/rebuild. Asset versions ended at
`style.css?v=20260721-6` / `app.js?v=20260721-6`. JS verified with `node --check` inside a
throwaway `node:20-alpine` container (no local node); grouping/behaviour verified by simulating the
real render logic against Fathima's live 32-turn conversation (`conv_e9fcc13d2feb`). DOM click-through
not automated here — visual confirmation via the user's screenshots.

**Fix 30 — Two views (`Detailed | Lineage`).** Added a tab strip (`#viewbar`) above the channel-filter
bar. `state.convView[conversation_id]` = `'detailed'` (default) | `'lineage'`. Both views render from
the same `buildUnits` output and theme grouping, so they never diverge. Channel bar's label renamed
"View:" → "Channel:" so the two bars don't both say "View".

**Fix 31 — Detailed shows ONE request.** `state.detailFocus[conversation_id]` holds a request key
(ticket-id, or `u<idx>` for unticketed). Default = the latest request (group 0, unit 0); a Lineage-row
click or a Tickets-panel jump (`goToConversation`) sets it. The stored focus is validated against the
current data each render and falls back to latest if it no longer exists. The group loop skips every
group/unit except the focused one; its theme header renders as a static (non-foldable) label.

**Fix 32 — Per-node fold removed from Detailed.** Request nodes always show their replies; removed the
chevron, the click/keydown toggle, and the `collapsedNodes`/`nodeSeeded` seeding + state. Theme-group
folding kept. The "Collapse/Expand all" button now toggles themes only and shows in Lineage only.

**Fix 33 — Detailed = stacked exchange rows.** Rewrote `renderUnit`: instead of a spine card with
sub-boxes, the focused request renders one **3-column row per exchange** (`.det-row`): Customer Query ·
middle (sentiment · ticket · channel · status · time) · **AI Agent Reply**, oldest→newest. This fixes
the multi-message ticket that previously showed one query + one reply. The middle-column sentiment pill
is per-exchange (from that inbound's urgency, since sentiment varies per message within a ticket);
middle column normalised to 10px; timestamp coloured `--t1` (black). Intent label dropped from the
query box; the reply box shows the auto-sent (holding) line above the AI reply when present and reply
text in full (no clamp).

**Fix 34 — Groups keyed by raw intent.** `themeOf` now returns the raw `intent` as the group key +
prettified label (via new `intentLabel`), instead of mapping to a team — so e.g. Fraud Report and
Transaction Dispute become separate groups (previously merged as "Fraud & Disputes"). Colour still
looks up the intent's team so related intents keep a shared colour family. `ticket_resolution` (a
system auto-resolve event, not a customer topic) is treated as unthemed via a new
`NON_TOPIC_INTENTS`/`topicOrEmpty` helper — everywhere intent feeds grouping AND the node/row titles —
so it never forms its own group and folds into its ticket's real intent. **Verified** on the real
32-turn thread: 9 clean groups, no ticket split across groups (incl. `tkt_785b7fe2e402` spanning two
loan messages), no standalone "Ticket Resolution" group. Note: a theme label can legitimately appear
more than once (two non-adjacent same-intent tickets = two groups, in time order — kept by choice).

**Fix 35 — Lineage = timeline strip.** Rewrote `renderLineageRow` (dropping the old 3-col query/reply
row and its first-Q/last-A pairing bug). Each request = a `.lin-row`: a narrow left `.lin-meta` section
(ticket-id + status stacked, divided) beside `.lin-main` = a mini timeline (`.tl`) with **one
channel-coloured dot per exchange** (`.tl-ex`: dot + channel label + time, oldest→newest) and a
one-line **"Opened with"** snippet of the opening customer message. Row's left border = **theme colour**
(`--lin-clr` = `themeColor.t`); dots stay **channel**-coloured — fixes the earlier border/header colour
mismatch. Click still drills into Detailed for that request. Removed the theme-header request count
(`ftd-count`; was only visible in Lineage and the "N requests vs N tickets" wording was ambiguous —
units include unticketed requests) and the redundant `.detail-back` "← Back to Lineage" button (the
Lineage tab already switches views). **Verified** (dot-per-exchange sim on real data): the two-message
Loan ticket = 2 dots; single-message tickets = 1 dot.

**Fix 36 — Orange view tabs.** Active `.viewtab.on` text + underline styled `#ea580c` (true orange;
`--amb-t` read as brown). Purely cosmetic.

### Also — Fathima HIL test questions (test data)
`docs/hil-test-questions.md` — added **Group 4 — More scenarios** (#13–#22) to Fathima's section:
10 questions grounded in her documented holdings (theft/under-review/approved claims, auto policy,
disputed ₹265 min-balance charge, ₹2,371 loan penalty, account-closure + switch-banks exit language,
avg-balance / pending-EMIs controls) so the Lineage / theme views have more requests across more
themes. Two helper columns ("Grounds on", "Expected"). L2 "Expected" values are best-guess (small-LLM,
non-deterministic — not run); the exit-language items rely on the deterministic attrition override.

### Fix 37 — Lineage ticket-id no longer clipped
**Problem:** in the Lineage view the `TKT_…` id pill showed truncated with an ellipsis (e.g.
`TKT_78587FE2E…`). Not a data issue — the full id is present; the fixed-width left meta column
was too narrow. `.lin-row` used `grid-template-columns:104px 1fr`, and the pill's
`max-width:100%;overflow:hidden;text-overflow:ellipsis` clipped the 16-char id to fit ~80px.
**Fix (CSS-only, `apps/admin-ui/style.css`):** changed the meta column from `104px` to `auto` so
it sizes to its content (pill + status) — exactly as wide as needed, no fixed guess, no gap. Kept
the pill's ellipsis but changed its cap `max-width:100% → 150px` so an unusually long id still
ellipsizes instead of stretching the row. Asset versions bumped `-6 → -8` in `index.html`
(intermediate `-7` was a first attempt at a fixed `136px`, which overshot and left a gap — replaced
by `auto`). Live via the bind mount; reload only. Visual confirmation via the user's screenshot.

### Fix 38 — Removed the inbox "Urgent" triage (redundant)
**Why:** the inbox surfaced high/critical conversations via an "Urgent" pre-triage — a red nav
badge, an "N urgent" count chip, an Urgent queue filter, and a per-row Urgent status pill. The
user judged this redundant: ticket **priority scoring** (backend, `services/ticket_service/priority_scoring.py`)
already scores risk into Low/Med/High/Critical, and the Needs-Review flow surfaces held escalations,
so the inbox's separate visual urgency flag added little.
**How urgency was derived (for reference — unchanged by this fix):** per-turn in
`services/intent_service/urgency.py` (`detect_urgency`): keyword net (fraud/blocked/stolen/overdue/
complaint/…) → `high`, negative sentiment → `medium`, else `low`; stored on each turn. The inbox read
the latest inbound turn's value as `last_urgency` (`repository.py` conversations query) and
`urgencyToStatus` mapped `high`/`critical` → `'urgent'`.
**Fix (frontend-only, `apps/admin-ui/`):**
- `index.html` — removed the `#inboxBadge` nav badge, the `#qcnt` "N urgent" chip, and the
  `data-f="urgent"` filter button (All + Needs Review remain).
- `app.js` — removed the badge/qcnt fill block in `loadConversations`; removed the
  `high/critical → 'urgent'` branch from `urgencyToStatus` (its resolved/active/open logic stays,
  still used by the row status pill and the header Resolve state); removed the
  `activeFilter === 'urgent'` branch in `renderQueue`; dropped the `'urgent'` cases from the row
  status dot/label (rows now read Resolved / Active / Open).
- `style.css` — deleted the now-orphaned `.durg{background:var(--red)}` dot-colour rule.
- Asset versions bumped `-8 → -9`.
**Not touched:** backend urgency (`detect_urgency`, `last_urgency`) and **ticket priority scoring**
are unchanged — this removed only the inbox's *visual* urgency triage. The settings-page
"Active / Not configured" inbox-connection badge (`inboxBadgeCls`/`inboxBadgeTxt`) shares a name but
is a different feature and was left as-is. Live via the bind mount; reload only. `node` not available
locally; DOM confirmation on next UI load.

### Fix 39 — Queue status label collapsed to Active / Resolved
**Why:** after Fix 38 the row status pill read Resolved / Active / **Open**, but "Open" is
unreachable: `conversations.status` is `NOT NULL DEFAULT 'active'` (`001_phase1.sql`), the only writes
set it to `active` or `resolved`, and a resolved conversation is flipped back to `active` when the
customer messages again (`repository.py`). The `|| 'open'` fallback in `urgencyToStatus`
(`app.js`) therefore never fires for real data, so "Open" was a label users never actually see. The
true distinction is binary: resolved vs not-resolved.
**Fix (frontend-only, display-only):**
- `app.js` — the row `stDot`/`stLabel` ternaries drop the "Open"/`dopn` branch: non-resolved →
  `desc` dot + "Active". `urgencyToStatus`'s internal `|| 'open'` return was left as a harmless
  default (its contract is unchanged; only the label stops printing "Open").
- `style.css` — deleted the now-unused `.dopn{background:var(--t3)}` dot rule.
- Asset versions bumped `-9 → -10`.
**Consequences (verified none):** `isDone`/header Resolve keys only on `=== 'resolved'`; every other
`'open'`/`'in_progress'` check in the UI is about **ticket** status (a separate field) — spine/lineage
node status, the Tickets panel, portal "My Tickets" `renderGroup('Open', …)` — all untouched. No
backend/schema/data change.

### Fix 40 — Detailed row left border matches the theme colour
**Problem:** in the Detailed view the exchange row's left border colour didn't match the theme
header above it (e.g. a purple-ish border under a pink `LOAN STATUS` header), while the Lineage view
matched. **Cause:** both views receive the same theme-colour object (`g.color`), but they coloured the
border differently — Lineage's `renderLineageRow` set `--lin-clr` to `themeColor.t` (theme colour, per
Fix 35), whereas Detailed's `renderUnit` set `det-row`'s `--det-clr` to `chn.clr` (the per-exchange
**channel** colour). Detailed already received `themeColor` but never used it for the border.
**Fix (frontend-only, `apps/admin-ui/app.js`):** in `renderUnit`, compute `themeClr =
(themeColor && themeColor.t) || 'var(--t3)'` (mirroring Lineage's fallback) and set the row's
`--det-clr` from it instead of `chn.clr`. `chn` is still used for the row's channel pill, so it's not
orphaned. Asset versions bumped `-10 → -11`. DOM confirmation on next UI load.

### Fix 41 — Unified status labels to Open / Resolved everywhere
**Problem:** the app has two status vocabularies — **ticket** status (`open` / `in_progress` /
`resolved`; enum in `shared/schemas/tickets.py`) and **conversation** status (`active` / `resolved`;
free-text SQLite column). The same "still being worked on" idea therefore rendered as four different
words across surfaces (inbox pill "Active", spine/lineage node "active", right-panel ticket pill
"open", portal My Tickets "Open"), which read as confusing near-synonyms. (`closed` also appears in
several frontend guards but the backend never writes it — inert.)
**Decision (user, after weighing keep-both vs unify):** collapse the *display* to one pair —
**Open / Resolved** — everywhere. Accepted tradeoff: `in_progress` now shows as "Open", so the UI no
longer distinguishes "picked up" from "not picked up" (that state is barely used and never set in the
normal flow; still fully functional in code).
**Fix (frontend-only, display-only — `apps/admin-ui/app.js`):** added `statusLabel(s)` →
`resolved`/`closed` ⇒ "Resolved", everything else ⇒ "Open". Wrapped it around the **6 display spans
only**: inbox queue pill, spine node pill, lineage node pill, right-panel ticket pill, portal
list pill, portal modal pill. Portal group headings were already "Open"/"Resolved".
**Why it's safe (verified by reading every site):** in each render site the status is used in two
separable roles — a raw value that drives logic (CSS class `statusCls`/`stBg`, `isOpen`, the Resolve
button, `nodeStatus`, and `resolveTicket`'s re-derivation at `app.js:1479-1483`) and a displayed
string. `statusLabel` is applied ONLY inside the `escH(...)` display spans; it never feeds a class,
branch, or comparison, and no code anywhere compares against a capitalized/renamed label or
round-trips a label back into logic. So colours, counts, filters, badges, priority sort, and the
resolve flow are unchanged. No backend/schema/DB/API change; enum + column values untouched. The
settings-page "Active / Not configured" inbox-connection badge shares the word but is unrelated and
was left as-is. Supersedes the "Active" label introduced in Fix 39. Asset versions bumped `-11 → -12`.
DOM confirmation on next UI load.

### Infra note this session
Docker Desktop shut down mid-session; all 6 project containers exited (255). Recovered with
`docker compose start` (data volumes intact — 5 real Neo4j customers + Fathima's conversation
preserved); API healthy on 8888 again. Not caused by the code changes (static bind-mounted assets).

---

## Session 5 — 2026-07-22 → 2026-07-23

Branch: `Sayantini-phase2-ui-changes`. Cross-sell / Up-sell "Suggested Offers" (Fix 42 family),
designed from the reference doc `docs/Call_Agent_Assist_Tool_CROSS_SELL_UPSELL_DESIGN.md` (nudge
engine from another project) adapted to async ticket-based chat. This project's own implemented
design is documented in `docs/CROSS_SELL_UPSELL_DESIGN.md`.

### Fix 42 — Cross-sell / Up-sell opportunity engine + admin flow
**Goal (user):** in a customer's chat, based on the recent conversation and/or the customer's
BFSI profile, the admin gets cross-sell and/or up-sell recommendations. User chose the
**LLM-driven** approach (doc-style) in a **separate Opportunities card**, and required that
**Approve executes something** (not decision-only like the old NBA Approve).

**Division of labour (the doc's core lesson):** CODE owns the guardrails — when to sell (gate),
what is offerable (deterministic candidate rules over Neo4j holdings/charges/conversation), and
validating the LLM only picked from that set. The LLM owns judgment — which ≤2 candidates fit the
recent conversation and a ≤20-word pitch grounded in the customer's real numbers.

**Pipeline** (`services/agent_assist_service/opportunity_engine.py`, new):
gate → `build_candidates` (10 rules, one candidate per product) → prompt (GOOD/BAD few-shot,
JSON-only contract, do-not-repeat list, last ~10 turns) → `GroqGenerator._generate`
(operation `opportunity_generation` → LLM observability for free) → `parse_and_validate`
(JSON cleanup; drops out-of-set products; `kind` always from OUR candidate, never the LLM's
claim; clamps; parse failure ⇒ fall back to stored pending rows — UI never blanks).

**Candidate rules (1–10):** loan+no life cover→term insurance · no health policy→health
insurance · account+no card→credit card · high balance (≥5× min)+no FD→FD · high balance→premium
account tier · FD maturing ≤90d→renewal · ≥5000 reward points (dpd<30)→premium card ·
**(8)** HNI/premium segment on entry variant (dpd<30 guard, user choice "a")→premium card ·
**(9)** ≥2 unreversed charges→charge-waiver account upgrade (sells by saving money) ·
**(10)** recent turn intent maps to an UNHELD product family→that product (loan_status/
loan_application→loan, card_management→card, policy_status→policy; FD/insurance questions
classify as general_inquiry in this taxonomy so rule 10 can't cover them — documented limitation;
family granularity is coarse: holding a Health policy blocks a term-insurance interest match).

**API** (`apps/api/routes/agent_assist.py`): `GET /admin/agent-assist/opportunities` — resolves
the Neo4j customer via channel identities (NBA `_load_graph_context` pattern), fetches context +
`get_charges`, normalizes turns to chronological (newest-first bug class from Fix 24g avoided),
runs the engine, persists new items into the existing `agent_assist_recommendations` table (no
migration), **dedupes by product against every prior row** — pending/approved/dismissed all
retire a product for that conversation ("one-shot"). Decision endpoint extended: **approving a
cross_sell/up_sell row creates an editable reply draft** (`channel="offer"` marker, pitch as
draft_text) after validating a push identity exists (400) and no other draft is pending (409 —
checked BEFORE flipping the recommendation). `repository.get_agent_assist_recommendation` added
(getter didn't exist).

**Dual-channel send** (`apps/api/routes/reply_drafts.py`): `send_draft` branches on
`channel=="offer"` → `_send_offer_draft` delivers the (edited) text to **every** push channel on
record — WhatsApp and/or email, missing ones skipped (user rule: "send to both; if one missing,
skip") — as a **fresh** mail (subject "An offer curated for you", no threading: an offer is not a
reply), one outbound turn per delivery (`metadata.source="opportunity_offer"`), draft→sent,
`offer_draft_sent` audit with the delivery list. Held-reply path untouched.

**UI** (`apps/admin-ui/`): right-panel **Opportunities** card (Cross-sell green / Up-sell amber
badge, pitch, "Why: <basis>" grounding line, Approve/Dismiss; suppressed state shows the gate
reason). Approve → `loadPendingDrafts()` + re-render so the draft card appears immediately.
Offer variant of the draft card: green, "💡 Approved offer — edit & send", "Send offer".

**Verified live:** engine exercised in-container on Fathima's real data (2 candidates, grounded
pitches, validation passed); Sayantini end-to-end **organically**: portal loan question →
rule 10 candidate + rule 9 (her real ₹3,791 AnnualFee+LateFee charges — disproving an earlier
wrong guess that she had none) → LLM items in the card → Approve → offer draft → Send →
delivered to **email only** (verified: her portal signup stored no WhatsApp identity — the
skip-missing rule working) → Mailpit mail → she replied to the offer email → reply landed in the
same conversation on the same ticket. Known LLM caveat surfaced: the pitch invented "12.99%
interest" (not in her data) — product/eligibility are code-validated, wording is not; the
admin's edit-before-send is the control. Tests: `tests/test_opportunities.py` (new) — gates,
all candidate rules, malformed-JSON/out-of-set/kind-override validation, pipeline with fake
generator, approve→draft→dual-send + 409/400 guards via TestClient. Suite at session end:
47 opportunity+agent-assist tests pass; full suite 4 pre-existing test_phase1 failures only.

### Fix 42a — Gates loosened to sentiment-only (sequence of user decisions)
Initial build had 4 gates (open ticket · negative latest message · fraud/dpd · attrition High).
Walked the user through what the reference doc gated (call-stage; only its "resolve first, sell
when receptive" maps here — fraud/dpd/attrition were our BFSI additions). User: **drop fraud/dpd
+ attrition** (42a-1), then — after the open-ticket gate forced send-reply+resolve clicks mid-
demo — **drop the open-ticket gate too** (42a-2). Shipped gate: ONLY "latest inbound message not
negative". The human admin reviewing every offer is the remaining judgment layer. `check_gates`
signature keeps `tickets` for future re-tightening; `score_attrition` import and the route's
`contacts_30d` plumbing removed as dead.

### Fix 42b — Rules 8–10 (folded into the rule list above)
Rule 8 chosen after the user challenged "gates pass but zero candidates" for Sayantini — audit
showed every rule correctly not firing on her data; the one real catalogue gap was HNI-on-Classic.
Rules 9+10 chosen from a practicality review (4-part test: grounded fact · customer benefit ·
one-sentence justification · data supports it). Explicitly REJECTED as not correct to build:
age/occupation demographic rules (profiling, no outcome data), loan pre-approvals (no credit
scoring), card limit increase (invented threshold), premium-due "offer" (duplicates the
Upcoming-event tile). `MAX_OPPORTUNITIES` stays 2 (doc lesson: fewer, better).

### Fix 42c — Removed the "Recommended actions" (NBA) card
Offer rows appeared in BOTH cards (same table; the NBA endpoint returns all pending rows —
a flagged-but-unapplied filter from the plan). User asked what NBA still does: 3 rules
(SLA-escalate / retention / KYC), all Approve-decision-only (dead-button problem from Fix 11),
two overlapping newer surfaces (Attrition band, Tickets panel). User chose **remove the card**
(consistent with Fixes 28/29/38). Frontend-only: card block + `renderNbaActions` + `decideNba`
deleted; backend engine/endpoint/tests kept; `_rule_cross_sell` + `_latest_sentiment` deleted
from the engine earlier in the session (superseded by the opportunity engine; its 5 rule tests
replaced by the new suite; `_load_graph_context` + its regression test kept).

### Fix 42d — Offer labelling in Lineage + Detailed
Sent offers rendered as ordinary "AI Agent Reply" rows with a blank Customer Query / "Opened
with —" (nothing pairs with a bank-initiated turn). Detection via `metadata.source ==
"opportunity_offer"` (verified present in the conversations API payload). Detailed: offer
exchange renders as "Bank-initiated / Offer approved by admin & sent" + amber **Offer** pill +
"Offer Message" box. Lineage: offer-only unit shows an **Offer/Sent** meta pill + "OFFER SENT
<text>" snippet; offer exchange dots get an amber ring + "Offer · <channel>" label.

### Fix 42e — Offer-glue grouping (user-corrected design)
**Problem (user):** the offer split its ticket — question `TKT_9C…` / offer / customer's
reply-to-offer (same `TKT_9C…`) rendered as THREE Lineage rows, because `buildUnits` merges only
consecutive same-ticket items and the unticketed offer broke adjacency (first-ever unticketed
turn injected mid-ticket; Fix 24a's "ticket never splits" held until now). First proposed rule
("absorb when sandwiched between same-ticket runs") was **rejected by the user as too narrow**;
the corrected principle: **an offer is not its own request — it glues to the request that
triggered it, and the customer's response to the offer continues that same request.**
**Implementation (frontend only):** `isOfferStep`/`isOfferTurn`; in the theme-group loop and in
`buildUnits` an offer item never starts a group/unit and is transparent to ticket adjacency
(`prevTicket`/`last.ticket` carry through, so same-ticket runs on both sides reunite); when the
offer is the newest turn (no unit yet), the next older item is adopted into its unit (offer
belongs to what triggered it); in the exchange builder an offer outbound starts its OWN exchange
(never overwrites the previous exchange's reply). **Verified by simulating the exact new logic
against her live turns:** loan request = ONE unit with 3 ordered exchanges (question→reply ·
OFFER · "I'm interested"→bank reply); FD/thank-you/dispute/card-limit units unchanged (7 units →
5). Screenshots confirmed by the user.

### Also — opportunity test scenarios in `docs/hil-test-questions.md`
Sayantini **Group 4** (#12–15): rule-10 loan question (marked consumed), rule-9 charge waiver,
sentiment-gate check, and the policy-family limitation documented as expected-nothing. Fathima
**Group 5** (#23–27): credit-card interest question (clears sentiment gate + rule 10), her three
data-driven offers, sentiment-gate check; **⚠ send caution** for her real email/WhatsApp on
non-local delivery modes (user's concern — she'd receive real mails). One-shot semantics noted.

### Decisions / open items
- Offer pitch **wording** can embellish (e.g. an invented interest rate) — grounding is enforced
  for product/eligibility only; admin edit-before-send is the control. A stricter "numbers only
  from basis" post-check was not built.
- "Thank-you" messages still create tickets (Rule 8 low_retrieval_confidence — no
  acknowledgement intent in the taxonomy) and aren't linked to the resolved ticket they refer to.
  Diagnosed in-session (design gap, not a bug); fix options discussed, deferred.
- Rule 10 family granularity is coarse (holding ANY policy blocks policy-interest matches);
  refining to sub-types (term vs health) discussed, deferred.
- Dismissed/suggested offers are retired per-conversation forever (no expiry window).
- Backend NBA engine + `/next-best-actions` endpoint remain API-only (no UI consumer).

### Infra / verification notes
- Multiple `docker compose build api && up -d api` rebuilds (backend baked into the image);
  frontend live via bind mount, asset versions `-12` → `20260723-3`.
- `node --check` via throwaway node:20-alpine container (MSYS_NO_PATHCONV=1 for the mount);
  grouping changes verified by Python simulation of the exact JS logic against live turn data
  before shipping.
- Changes remain **uncommitted** on `Sayantini-phase2-ui-changes`.
  (Committed after session close as `4f2f85c`.)

---

## Session 6 — 2026-07-23

Branch: `Sayantini-phase2-ui-changes`. Inbox-row declutter.

### Fix 43 — Removed the inbox-row status dot + label
**Why:** after Fix 38 (Urgent removed) and Fix 41 (labels unified), the queue-row status is strictly
binary Open/Resolved — and a resolved row is already visually distinct twice over (the `done` class
dims the row; the dot flipped amber→green). The text label was a third encoding of the same bit, and
"Open" on nearly every row carried no information (same reasoning as Fix 39). User reviewed the
options (drop status only / drop pill too / keep pill drop stripe) and chose **drop the status
dot+label only** — channel pill and stripe stay.
**Fix (frontend-only, display-only — `apps/admin-ui/`):**
- `app.js` — `renderQueue`: removed the `stDot`/`stLabel` derivation and the `.sl`/`.sd` status span
  from the row template. `sts` (`urgencyToStatus`) is still computed — it drives the `done` row class
  and selection state. `statusLabel()` keeps its 5 other display sites (spine, lineage, tickets
  panel, portal list + modal) — verified by grep.
- `style.css` — deleted the now-orphaned `.sl`, `.sd`, and the `.dbot`/`.desc`/`.dok` dot-colour
  line (`.dbot` was already dead — no JS/HTML reference anywhere).
- `index.html` — asset versions bumped `20260723-3/-4 → -5` (both files now on `-5`).
**Verified:** `node --check` via throwaway node:20-alpine container — syntax OK. Live via the bind
mount; DOM confirmation on next UI load.

### Fix 44 — Snapshot tile renamed "Upcoming event" → "Deadline"
**Why:** the name was subtly wrong for the tile's highest-value state — an *overdue* item (e.g.
"Card payment · 45d overdue") is a past event, and "event" reads like a calendar appointment
rather than a money deadline. All three data sources (card payment due, FD maturity, policy
premium due) ARE deadlines, so "Deadline" is true in every state the tile renders (overdue /
today / in Nd). Chosen after weighing Key date / Next due / Account alert / Needs attention etc.
("Next due" fails FD maturity; "Account alert" overstates a calm upcoming item).
**Fix (frontend-only, display-only — `apps/admin-ui/app.js`):** one display site — the `.ml`
label in the Profile Snapshot tile ("Upcoming event" → "Deadline") and its native tooltip
("product event" → "product deadline"). Backend field stays `upcoming_event` (API contract
untouched). Asset version bumped `-5 → -6` (app.js only). `node --check` OK.

### Fix 45 — Sentiment panel: "(last N messages)" made true
**Problem (found reading the code while explaining it):** the right-panel Sentiment card's
"(last 5 messages)" caption was fiction on two levels: (1) the counts/percentages/label were
computed over **ALL** inbound turns in the conversation — `msgCount = Math.min(inbound.length, 5)`
was used only to print the caption, never to slice the data; (2) the caption number was then
clamped **by verdict** (`Frustrated → min(…,3)`, `Very frustrated → min(…,4)`) — cosmetic
storytelling with no computation behind it, and backwards (the verdict changed the claimed window).
A conversation angry long ago but calm now still read "Frustrated (last 3 messages)".
**Fix (user chose "make the computation match the caption" over relabelling; frontend-only,
`apps/admin-ui/app.js` `renderRight`):** `recent = inbound.slice(-SENT_WINDOW)` (SENT_WINDOW=5) —
counts, percentages, bar, and headline label all now derive from that same window; caption shows
the real window size (`recent.length`, < 5 for short conversations); per-verdict clamps deleted.
Label thresholds unchanged (neg≥60 Very frustrated / neg≥30 Frustrated / pos≥55 Positive / else
Neutral). **Ordering verified before shipping:** `conv.turns` is chronological — `list_recent_turns`
selects `DESC` then `reversed(rows)` (`repository.py:262-265`) — so `slice(-5)` takes the newest 5.
Known consequence: with a 5-message window the bar shows multiples of 20% (correct trade for
"how do they feel now"; lifetime mood remains the attrition scorer's bad-mood sign, backend).
Asset version bumped `-6 → -7`. `node --check` OK.

### Fix 46 — Sentiment + Profile-snapshot merged into one right-panel card
**User request:** drop the "Profile snapshot" heading and put both sections under the same grey
area. **Fix (frontend-only):** `app.js` — the two sibling `.rpcard` divs in `renderRight` became
one; the `rplbl` "Profile snapshot" line deleted; the attrition band + `mgrid` tiles now sit in a
new `.snap-sec` wrapper inside the same card. `style.css` — `.snap-sec{margin-top:12px;
padding-top:12px;border-top:1px solid var(--bdr)}` gives a subtle divider between the sentiment
block and the tiles (border on the wrapper, not the attrition band, because the band is
`display:none` until the async /graph fetch fills it — the divider must show regardless). All
`snap-*` ids unchanged, so the async fill code needed no changes. Asset versions bumped → `-8`
(both files). `node --check` OK.

### Fix 47 — Right-panel Tickets card: open-only + one-ticket-height scroll
**User request:** show only open tickets, header "Open Tickets (N)", and cap the scroll area at
one ticket's height. **Fix (frontend-only):**
- `app.js` `renderRight` — the `convTickets` filter now also requires
  `status === 'open' || 'in_progress'`; header "Tickets (N)" → "Open Tickets (N)" (count = open
  only). When a conversation has zero open tickets the card doesn't render at all (pre-existing
  no-tickets behaviour, now also the all-resolved case).
- `style.css` — `.tkt-scroll` `max-height:360px → 118px` (~one open card: padding 18 + head 16 +
  title 16 + created 14 + Resolve button ~32 + margin 6); additional open tickets scroll, the
  header count signalling there are more.
- **Checked before shipping:** `resolveTicket` re-derives + calls `renderRight` with fresh ticket
  data, so a just-resolved ticket cleanly drops out of the list (and the card disappears on the
  last one) — no stale-row path. Resolved history remains visible in the Lineage view and the
  portal My Tickets. The row's resolved-styling branch (`stBg`/`statusLabel`) is now unreachable
  in this card but left in place (harmless).
Asset versions bumped `-8 → -9`. `node --check` OK.

### Fix 48 — Connectors page: two false "Disconnected" badges + email-card naming
**Problem (user: "why does the connector page look weird? two mail connectors? Jira
disconnected?"):** three distinct issues, diagnosed by calling all four status endpoints live
with the admin key before changing anything:
1. **Gmail SMTP showed "Disconnected" while mail demonstrably sends** (Session 5's offer emails
   delivered). Cause: frontend read `emRes.configured` but `/admin/email/status`
   (`SMTPEmailConnector().status()`) has NO `configured` field — its readiness flag is
   `gmail_ready` (live: `true`). `undefined` → falsy → permanent "Disconnected".
2. **Jira CRM showed "Disconnected" as a hardcoded literal** (`status:'disconnected'` in the
   connectors array) — the real `/admin/crm/status` endpoint existed but was never called; live
   it returns `configured: true` (full Jira env config present), and the pipeline actually
   reaches Jira (the known 400 proves contact).
3. **"Two mail connectors" is correct but unreadable** — Gmail SMTP (outbound) vs Email Inbox
   IMAP (inbound) are two directions of the same account, presented as near-identical red
   envelope cards.
**Fix (frontend-only, `apps/admin-ui/app.js` `loadConnectors`):** SMTP badge now keys on
`gmail_ready`; added a `/admin/crm/status` fetch and the Jira card uses it (`configured` →
Connected); cards renamed **"Email · Outbound (SMTP)"** / **"Email · Inbound (IMAP)"** with
direction-first descriptions. WhatsApp (`connected:true`, matches) and IMAP ("Active", matches)
untouched; "Last poll: Never" was just the poller not having run yet — not a bug. Known
remaining sloppiness (not fixed): a failed status *fetch* still renders as "Disconnected"
rather than "Unknown" (all catches swallow). Asset version bumped `-9 → -10` (app.js).
`node --check` OK.

### Fix 48a — Connectors: merged Email card + ordering
**Why (user: "why does email come twice?"):** inbound (IMAP poller) and outbound (SMTP sender)
are genuinely two independent pipes with separate failure modes — but that's an implementation
truth, not a user-facing one; to an admin, Email is ONE channel, and two peer cards leaked the
plumbing. **Fix (frontend-only, `apps/admin-ui/app.js` `loadConnectors`):** removed the
"Email · Outbound (SMTP)" entry from the simple-cards array; the extended IMAP card became the
single **"Email"** card — its stats grid now leads with two per-pipe rows (**Inbound (IMAP)** /
**Outbound (SMTP)**, each Active/Down) above Mailbox / Poll interval / Last poll / Emails
processed, keeping the Poll-now button and error line. Card badge: **Connected** (both up) /
**Partial** (one up — reuses the `disconnected` badge style) / **Disconnected**. Inserted via
`grid.insertBefore(..., grid.children[1])` so the order is **WhatsApp · Email · Call · Jira CRM**
(channels first, back-office last). **Call kept** by user choice (Phase-2 roadmap visibility).
Asset version bumped `-10 → -11`. `node --check` OK.

### Fix 49 — Removed the standalone Tickets page
**Reasoning (user asked for it explicitly + "why removing is correct"):**
1. No real user at scale — agents work assigned queues (inbox), supervisors need scoped
   worklists with assignment/SLA (this page had neither), managers need aggregates (Analytics),
   auditors need single-ticket lookup (inbox search / right-panel). A flat browse-everything
   table serves nobody's actual job.
2. The architecture already names its replacement: every ticket is pushed to **Jira CRM**
   (`ticket_manager` → `crm_sync_status`; Connectors card now truthfully Connected). Keeping a
   homegrown 1% re-implementation alongside the integration contradicts the design's own story.
3. Read-mostly dead weight — resolve/reply happen in the inbox. (Correction found during
   removal: rows WERE clickable into conversations via `goToConversation` — the earlier
   "read-only" claim was wrong on that detail; the other arguments stand.)
4. Technically unscalable — fetched ALL tickets and filtered client-side in JS.
5. Consistent with the session arc (Fixes 38/29/42c/43/47): one authoritative home per fact.
**Reversibility (user requirement):** the page exists complete in git history; this removal is
its own commit — `git revert` restores it wholesale. Nothing else needed.
**Removed:** `index.html` — nav item (`#nav-tickets` + `#ticketsBadge`) and the 126-line
`#page-tickets` block. `app.js` — `loadTickets`, `filterTickets`, `onTktDateChange`,
`clearTktRange`, `applyTktFilters`, `tktCustomerCell`, `renderTicketRows`, `tktSlaCell`,
`fmtDuration` (only caller was `tktSlaCell`), `_convMap`; the `switchPage` tickets branch, the
SSE-handler tickets/badge branch, and the 10s fallback-poll timer. `style.css` — the 47-line
`.tkt-page`…`.pri-low` block (deleted via a guarded Python script asserting no right-panel
class was inside).
**Kept (verified each):** `_allTickets` cache — fed independently by `loadConversations()`, so
inbox status derivation, spine/lineage `tktStatusMap`, `selectConv`, and the right-panel Open
Tickets card all work unchanged; `fmtDateTime` (shared by right panel + portal);
`goToConversation`; all right-panel `.tkt-item`/`.tkt-scroll`/`.tkt-resolve-btn` CSS (grep: 10
refs remain). `resolveTicket` rewired to drop its `loadTickets()` step — its
`loadConversations()` call already refreshes the cache it re-derives from. Backend
`/admin/tickets` endpoint untouched (still consumed by `loadConversations`).
**Verified:** repo-wide grep — zero dangling references to any removed symbol/id; `node
--check` OK. Asset versions bumped → `-12` (both files).

### Fix 50 — Coloured "Open Tickets" + "Suggested Offers" headings
**User request:** show those two right-panel headings in colour (chose "just those two" over a
uniform accent on all three). **Open Tickets → amber** (`--amb-t` — matches the app's
open-ticket accent: Open pill, ticket labels). **Suggested Offers → purple** (`--pur-t`), the
user's pick after two rejected attempts: green `--grn-t` (looked washed-out at 10px uppercase)
then orange `#ea580c` (applied without waiting for the user's choice — process slip, called
out; superseded). Sentiment heading stays muted grey.
**Fix (frontend-only):** `app.js` — added `rplbl-tickets` / `rplbl-offers` classes to the two
heading divs; `style.css` — two one-line colour overrides under `.rplbl`. Asset versions bumped
`-12 → -15` across the iterations. `node --check` OK.

---

## Session 7 — 2026-07-23 → 2026-07-24

Branch: `Sayantini-phase2-ui-changes`. Omnichannel demo testing for Sayantini (`CRN00010001`)
surfaced a cross-channel ticket-continuity bug; fixed with a scope-refinement guard (Fix 51,
which had already been drafted+manually-tested but never logged) and a new tier-4 LLM ticket
referee (Fix 52). Fresh-start reseed done at session open (wiped `cx-data` + `neo4j-data`, kept
`ollama`/`huggingface`/`opensearch`; 5 BFSI customers reseeded, empty inbox).

**How the bug was found (live):** Sayantini opened a dispute by **email** ("I need help disputing
a transaction"), added specifics by **web chat** ("Rs. 4,500 at TechMart on my Mastercard"), then
asked by **email** "Any update on my dispute?". The last message created a **second ticket**
(`TKT_B32E…`) instead of continuing the first — the exact opposite of the omnichannel promise
("I couldn't find any information about a transaction dispute request in your account context").

### Fix 51 — Ticket scope refinement (vague → specific)
**Context:** `_ticket_scope` (`ticket_manager.py`) tags each escalating message by keyword —
`transaction_dispute:card` / `:upi` / `:other` (vague fallback). Ticket reuse matched on
**exact scope-string equality**, so a vague opener (`:other`) followed by a specific follow-up
(`:card`) forked a duplicate.
**Fix (backend, `services/ticket_service/ticket_manager.py`):** when a **specific** scope matches
no active ticket, look for an active `:other` ticket of the same intent and **refine it in place**
(`_refine_ticket_scope`: update `ticket_scope` in metadata, write a `ticket_scope_refined` ticket
event + audit). Only `:other` is upgradeable — two different specific scopes (card vs upi) are
distinct incidents and still fork. **This code + its test had been written in an earlier manual
session and left uncommitted/unlogged;** verified this session (`test_specific_scope_refines_open_
other_ticket_instead_of_forking` passes) and folded into the log.

### Fix 52 — Tier-4 LLM ticket referee (specific → vague) + description refresh
**Why Fix 51 alone was incomplete:** the refinement only looks *up* the specificity ladder. A
status-style follow-up ("any update on my dispute?") carries no card/upi keyword → scopes `:other`
→ but after refinement no `:other` ticket exists → forks. A vague follow-up is the *signature* of a
cross-channel continuation (channel-hopping strips detail), so this hit the omnichannel story
directly. Ticket identity is decided by deterministic keyword+SQL, not the LLM — so the LLM did not
"fail"; it was never consulted for this decision.
**Design (agreed after weighing pure-deterministic vs LLM):** tiered — deterministic where certain,
LLM only where genuinely ambiguous, safe default always.
1. exact scope match → attach (existing)
2. specific scope + active `:other` → refine (Fix 51)
3. no match + 0 active same-intent tickets → new ticket
4. **no match + ≥1 active same-intent ticket → LLM referee** (`_referee_match`): given the message
   + each **code-vetted** candidate (active, same intent, same conversation), answer a ticket id or
   NEW. Validation: answer must be a candidate id, else NEW. LLM error / down / no generator → NEW.
   **Doubt forks, never merges** (a fork is visible+fixable; a silent merge corrupts the record).
   Attach writes a `ticket_referee_attached` event + audit.
**Root-cause found mid-fix (via prompt/answer dump):** the referee initially mismatched because a
refined ticket's `description` was **frozen at the vague opener** ("please help") — it never
contained the details ("TechMart/Mastercard") that arrived later, so the model matched against a
summary missing its own defining facts. **Two-part fix:** (A) surface the scope **subtype** as a
human-readable discriminator in the prompt (`_scope_label`: `transaction_dispute:card` →
"card transaction dispute"); (B) `_refine_ticket_scope` now **appends the new details to the ticket
description** (`update_ticket` allow-list gained `description`) — also improves the admin ticket
card / Lineage, which showed only "please help" before.
**Files:** `services/ticket_service/ticket_manager.py` (referee, `_scope_label`, description
append, `generator` param — no default, so TicketManager stays LLM-free unless wired);
`services/persistence_service/repository.py` (new `list_active_tickets_for_intent`; `description`
in `update_ticket` allow-list); `services/orchestration_service/graph.py` (shares the ticket
agent's generator into the manager — the only production wiring change).
**Real-LLM spot-check** (`llama-3.1-8b-instant`, 5 runs/case, in-container against grounded
tickets):
- "any update on my dispute?" with **1** open ticket (the live demo state) → CARD **5/5** ✅
- "the TechMart charge" with 2 open tickets → CARD **5/5** ✅ (0/5 before the description fix)
- "the UPI one" with 2 open → UPI **5/5** ✅
- new incident (gym double-charge / FlyHigh ₹12,300) → NEW **5/5** each ✅
- **Residual limitation (accepted, not a bug):** a *bare* "any update on my dispute?" with **two**
  open disputes is genuinely ambiguous (no distinguishing words) — the model picks one; a human
  agent would also guess. It never wrongly forks and never merges a new matter. The moment the
  customer names anything ("the card one"/"the UPI one") → correct 5/5.
**Tests (`tests/test_phase1.py`):** 6 new referee tests + the extended refinement test — vague
cross-channel follow-up attaches (via `_FakeRefereeGenerator`), NEW verdict forks, no-generator
forks, hallucinated out-of-set id forks, LLM error forks, and picks the *older* of two candidates
by the LLM's answer (proving not-recency). Full suite: **135 pass, 4 pre-existing test_phase1
failures only** (confirmed identical with changes stashed).
**Live:** api image rebuilt 3× this session; referee is live. The demo conversation created before
the fix keeps its duplicate `TKT_B32E…` (not retroactively merged — the fix applies to new
messages). Changes **uncommitted** at session end.

### Fix 53 — Offer send: dedupe push channels by normalized destination
**Found live (Sayantini offer demo):** an approved personal-loan offer showed as TWO identical
"OFFER · WHATSAPP" turns (+ one email) in Lineage/Detailed. **Root cause (verified against live
data):** her customer record carried the same WhatsApp number twice —
`whatsapp | 7890864700` AND `whatsapp | 917890864700` (bare vs. `91` country-code) — because the
inbound path only does `.lstrip('+')`, which never strips `91`. `_send_offer_draft`
(`apps/api/routes/reply_drafts.py`) loops over every whatsapp/email identifier and delivers one
message + one outbound turn per row, with no dedupe → the same person messaged twice.
**Fix (backend, `apps/api/routes/reply_drafts.py`):** added `_push_dedupe_key` (email →
`email:<lowercased>`; whatsapp → digits only, drop a leading `91`) + `_dedupe_push_identifiers`
(keep first per key, order preserved), applied to the push list before the send loop. One message
per real destination now.
**NOT this fix (deferred, deeper):** the *duplicate identifier row itself* — identity resolution
should normalize phone numbers on write so `7890864700` and `917890864700` never both exist (Fix 1
territory; needs a reseed to verify). This is the symptom fix per "simplest working option first";
the held-reply path (non-offer) delivers on the single arriving channel so it isn't affected.
**Verified:** 3 new unit tests (country-code collapse, distinct destinations kept, email
case-insensitive) — `tests/test_opportunities.py` 37 pass; live in-container check on her real
identifiers: push list 3 → 2 (one email + one whatsapp). api rebuilt; live.
**Also surfaced this session (logged as known caveats, NOT fixed — pre-existing, unrelated to the
ticket/offer code):** (1) an irrelevant "personal loan requirements" paragraph in a dispute answer
— weak RAG retrieval on a detail-less query pulled an off-topic KB chunk and the 8B model ignored
its "don't volunteer unrelated products" rule (answer is generated at `resolve_query`, two steps
BEFORE any ticket work — confirmed not caused by Fix 51/52); (2) email-channel replies greet
"Sayantini S 55" (the email-derived username) instead of her real Neo4j name — Fix 6 name
propagation may not cover the email path. Both are answer/identity-quality gaps for a later
session.

### Fix 54 — Connectors page: Web Chat card + trimmed Email card
**User requests (demo prep):** (1) add Web App / Web Chat as a connector after Email; (2) the Email
card showed "so many info" — too much plumbing for a client-facing page.
**Fix (frontend-only, `apps/admin-ui/app.js` `loadConnectors` + `index.html` asset bump
`20260723-13` → `20260724-1`):**
- **Web Chat card** — new simple card (blue chat icon, "Customer portal · in-app chat (synchronous
  inbound + reply)", always **Connected** since it's served by this same app). Inserted at grid
  index 2 (after the Email card, which itself is inserted at index 1), giving order
  **WhatsApp · Email · Web Chat · Call · Jira**.
- **Email card trimmed** (user chose "keep Inbound/Outbound only") — kept the badge + the two pipe
  rows (Inbound IMAP / Outbound SMTP Active/Down); removed Mailbox / Poll interval / Last poll /
  Emails processed and the **Poll now** button. Reason: operational detail is demo-noisy, and
  "Last poll: Never / Emails processed 0" made a Connected card look broken.
- `triggerEmailInboxPoll` and the `inboxLastPoll`/`inboxProcessed`/`inboxPollBtn`/`inboxPollStatus`
  ids are now unreferenced (button removed) — dead but harmless; left in place to avoid a wider
  edit before the demo. Unused vars (`lastPollTxt`/`processedTxt`/`intervalTxt`/`mailboxTxt`/
  `errorHtml`) likewise left.
**Verified:** `node --check` (throwaway node:20-alpine) — JS OK. Live via bind mount; reload only.

---

## Session 8 — 2026-07-25

Branch: `Sayantini-phase2-ui-changes`. Omnichannel WhatsApp demo debugging. The session was mostly
**diagnosis of environment/ops issues** (no code bug in most of them), plus two small code fixes.

### Diagnosis 1 — "AI responses became poor after a fresh start" = Groq daily token quota exhausted (NOT a code bug)
**Symptom (user, live demo):** after a ~10am fresh start, WhatsApp/portal AI replies turned poor —
unrelated to the query, dumping random KB facts and a `Source: [1] InboxIQ_BFSI_KB.pdf:p1` line to
the customer, and omnichannel ticket continuity broke (duplicate dispute tickets). Fine at ~11:53am,
bad again at ~12pm.
**Root cause (proven from the `llm_usage_events` table in the api container):** all 32 of the day's
LLM failures were the identical Groq error — **HTTP 429, "tokens per day (TPD): Limit 500000, Used
499508."** The free-tier **500K-tokens/day** cap was exhausted. One quota feeds EVERY LLM call
(answer generation, intent classification, resolution-level, ticket referee, opportunity generation),
so when it's dry they all fail together — explaining all three symptoms at once. The intermittent
on/off (fine 11:53, bad 12:00) is sitting right at the rolling-window edge. The chronological log
matched the screenshots exactly (times are UTC; ~10am–12pm IST = ~04:30–06:30 UTC).
**The fresh start did NOT burn tokens** — verified: reseed makes ZERO Groq calls (Neo4j loader has no
LLM refs; KB indexing uses a LOCAL `SentenceTransformer`, not Groq). What drained the cap was the
round of demo **test conversations** (~4–5 large Groq calls each; opportunity_generation was the
heaviest — 24 calls). **Quota is a rolling 24h window, not a midnight reset** — tokens fall off ~24h
after spend. By later the same day the window had fully rolled off (0 tokens used in trailing 24h →
full 500K/500K again), and the ORIGINAL key worked again — no key swap needed. A spare Groq key was
obtained and held in reserve (a second key on the SAME org shares the 500K; only a different account
gives a fresh 500K).

### Diagnosis 2 — ngrok kept using the OLD domain after `.env` edit = PowerShell env-var precedence (NOT a rebuild issue)
**Symptom:** user changed `NGROK_DOMAIN`/`NGROK_AUTHTOKEN` in `.env` and rebuilt, but ngrok logs still
showed the old `smartly-shredder-overhang…` domain. **Root cause:** the ngrok `command:` `--url` is
interpolated by `docker compose` at container-create time (stock image — `docker compose build` does
nothing for it), AND a **stale `NGROK_DOMAIN` was exported in the user's PowerShell session**. Compose
ranks **shell env > `.env`**, so the old shell value shadowed the corrected `.env`. `docker compose
config` (run from a clean Bash shell) resolved the NEW value, proving `.env` was right — the shell was
the culprit. Also caught a stray trailing slash in the new value (removed). **Fix:** recreate from a
shell where `NGROK_DOMAIN` is not exported → `docker compose up -d --force-recreate ngrok` → tunnel
came up on `tactical-dribble-booting.ngrok-free.dev`. (Same precedence lesson applied to every
subsequent container recreate this session.) User updated + verified the WhatsApp webhook URL.

### Diagnosis 3 — WhatsApp reply not arriving = expired Meta access token (NOT the LOCAL_TEST_MODE flag)
**Symptom:** inbound WhatsApp message appeared in admin-ui and the LLM answered correctly (FD maturity,
NO TICKET — correct L1), but nothing arrived on the customer's phone. **Root cause (from api logs):**
outbound delivery failed 3× with **`httpx.HTTPStatusError: 401 Unauthorized`** on
`graph.facebook.com/v19.0/{phone_id}/messages`; Meta `debug_token` confirmed **"Session has expired on
23-Jul"** (OAuthException code 190). The `WHATSAPP_ACCESS_TOKEN` had expired ~2 days earlier.
**Correction to a prior belief (memory `connectors-page-truth` updated):** `WHATSAPP_LOCAL_TEST_MODE=true`
does NOT simulate the production outbound path — verified it's read only in `security.py` (inbound
signature relax) and the `/test/whatsapp/*-simulate` endpoints; the real adapter
`channel_adapter/whatsapp_meta.py::send_outbound` always calls Meta. So real replies really send, and a
bad token surfaces as a live 401. **Fix:** user generated a new token (validated via `debug_token`:
`is_valid:true`, scopes `whatsapp_business_messaging`+`management`, expires ~7 Aug) → put in `.env` →
recreated api from clean shell → **outbound confirmed: reply arrived on the customer's WhatsApp phone.**
Note for durability: this token still expires (~2 wks); a permanent System User token would avoid recurrence.

### Fix 55 — Line breaks render in the Detailed conversation view (CSS-only)
`.det-q-text` (customer query) and `.det-r-text` (AI reply) in the Detailed 3-column view were missing
`white-space:pre-wrap`, while every other reply surface (`.spine-reply-text`, portal `.portal-chat-msg`,
ticket modal `.utd-resp`, old flow view) had it. So a multi-line AI reply / multi-paragraph email answer
collapsed into one run-on block **only in Detailed**. Added `white-space:pre-wrap` to both classes
([style.css:520,527](../apps/admin-ui/style.css)); cache-bust `style.css?v=20260723-15 → 20260725-1`.
Frontend-only, display-only, live via bind mount (reload only). The `*bold*` asterisks the user asked
about are intentional WhatsApp markdown (renders bold on the phone; admin-ui shows them raw in all
views — not a bug).

### Fix 56 — Graceful fallback when the LLM is unavailable (no more raw KB dump to the customer)
The defect Diagnosis 1 exposed: when generation returns `llm_used=False`,
[rag_pipeline.py](../services/rag_service/rag_pipeline.py) `answer()` sent the customer the **raw top KB
passage + internal `Source: [1] …` citation** (the ugly 12pm output). Replaced that branch — collapsed
the two non-LLM branches into one clean holding message ("I'm having trouble accessing that information
right now. Let me connect you with a support specialist who can help you further."), and dropped the old
`else`'s false "a support ticket has been created" promise (this path creates no ticket). Backend, but
happy-path unchanged (only the LLM-failure text changed); `retrieval_backend`/`citations` telemetry
intact. **Chose Option 1 (fix the text)** over Option 2 (route LLM-failure into the human-in-the-loop
draft hold) — Option 2 is the stronger real-ops behaviour but touches orchestration; noted as a
follow-up. **Verified:** forced-failure in-container → holding message returned, `Source:[1]` gone,
citations/backend still populated; `tests/test_phase1.py -k "rag or fallback or keyword"` 8/8 pass (no
test asserted the old fallback text — checked before applying). Backend change: **needs an api image
rebuild to persist** (hot-copied into the running container for verification this session).

### Open / follow-ups
- ~~**api rebuild pending** to bake Fix 56 (backend)~~ **RESOLVED** — the api image was rebuilt +
  recreated after the fix (image built 2026-07-25T08:34:02Z, container recreated 12s later off it).
  Verified: source is committed (`81e90ed`) AND the running container carries the fix (grep inside
  `omnichannel-cx-project-api-1` → `/app/services/rag_service/rag_pipeline.py:64` = the holding
  message; no `Source:[1]` dump, no false "ticket has been created" promise). Fix 56 is baked in;
  a `--force-recreate` no longer reverts it.
- Permanent WhatsApp **System User token** (never-expires) recommended before the real demo to avoid
  recurring token expiry.
- Groq **spare key** held in reserve; single key = ~100+ conversations/day of headroom — don't burn it
  on rehearsals. Watch `opportunity_generation` (biggest per-message token cost).
- Option 2 (LLM-failure → held draft for agent) deferred.

### Addendum (later 2026-07-25) — token expiry recurrence + fresh-start runbook
- **WhatsApp token expired AGAIN** (3rd time). Sayantini's WhatsApp dispute reply never reached her
  phone: AI generated it fine + ticket `tkt_6b8277693831` created, but outbound Meta delivery
  **401'd** (`graph.facebook.com/v19.0/1161808003684702/messages`). Investigated properly this time
  (not assumed): confirmed the container **was** using the updated `.env` token (prefix match) and
  the phone-id matched — then Meta `debug_token` gave the authoritative cause: **code 190, "Session
  has expired 25-Jul-26 03:00 PDT."** So the recently-updated token was **short-lived** and died
  within hours. User swapped in another token + `--force-recreate api` (from clean shell) → verified
  valid, BUT `debug_token` shows it expires **2026-07-25 12:00 UTC (17:30 IST)** — still temporary.
  **The permanent fix remains the System User token** (never-expires) — this keeps recurring until
  that's done. Also spotted (not the cause, logged for later): a latent async bug in
  `services/channel_service/delivery.py::_run_async` (`RuntimeError: no running event loop` on one
  send path) — separate from the token 401.
- **NEW: [docs/fresh-start-runbook.md](fresh-start-runbook.md)** — verified, repeatable full-wipe +
  real-WhatsApp procedure. Written because "fresh start" kept hitting DIFFERENT deps each time (Groq
  quota, ngrok domain, WhatsApp token). Covers: which 3 volumes to wipe vs 2 to keep (exact names),
  Neo4j **auto-reseeds on api startup** (only when graph empty — no manual seed needed), KB re-index
  is manual, the clean-shell env-precedence trap, and an **⑧ verification checklist covering ALL 7
  external deps** (Groq key+quota, Ollama, WhatsApp token, ngrok, Neo4j, OpenSearch/KB, SMTP/IMAP/CRM)
  — each with its real `:8888` status endpoint. Honest caveat documented: after wiping `cx-data` the
  local Groq usage table is empty, so it can't report the *account's* server-side rolling-24h quota;
  a single `max_tokens=1` probe is the one deliberate real Groq call to confirm key+quota.
- **Nothing wiped yet** — runbook authored + reviewed; the destructive wipe was NOT executed this
  session (awaiting user go-ahead + a permanent token).

### Fix 57 — Customer name correct in admin inbox + reply greetings (backend, api rebuilt)
**Symptoms (user):** admin portal customer names displayed wrong; email AI reply used a wrong name;
WhatsApp/web-chat replies didn't use the customer's name. **Root cause (traced, not assumed — one bug
underlies all three):** `display_name` feeds BOTH the admin inbox and the reply salutation
(`graph.py` → `compose_answer(customer_name=state.customer["display_name"])`). At
`_resolve_identity`, for whatsapp/email channels the code set `message.display_name =
neo4j_profile["email"]` — **discarding the real `name` that `get_customer_by_identifier` already
returns** (`queries.py` selects `c.name`). Downstream `_salutation()` then reconstructs a name from
that email's local-part → `sayantini.s.55@…` becomes **"Sayantini S 55"** (Symptom 2), and the admin
inbox shows the email-derived string (Symptom 1). Separately, `compose_answer` only added a greeting
on the **email** branch — WhatsApp/web (`return body`) had **no greeting/name at all** (Symptom 3).
**Fix (2 edits):**
1. `services/orchestration_service/graph.py` (~L246-257) — when the Neo4j profile has a real `name`,
   set `display_name = neo4j_profile["name"]` (still only overriding generic/blank names; `linked_email`
   still stored in metadata). Fixes Symptoms 1 + 2 at the source.
2. `services/agent_service/orchestration_agents.py` (`compose_answer`, ~L625) — WhatsApp/web now
   prepend `Hi {salutation_name},` using the same real name; `_salutation` falls back to "Customer"
   for unknowns, so nothing breaks for unregistered senders. Fixes Symptom 3.
**Verification (ZERO real Groq calls — per user's quota reminder):** `_salutation` unit probe (real
name→"Sayantini Sarkar", email→old mangled value on the now-dead path, empty→"Customer");
`tests/test_user_portal.py` 12/12 pass; the 3 failing `test_phase1.py` tests
(`test_email_complaint_escalates_and_sends_reply`, `..._webhook_e2e...`, `..._masks_pii..._restores_name`)
proven **pre-existing** by stashing the changes and reproducing the identical
`Recorder.send_text() got an unexpected keyword argument 'reply_to_message_id'` mock-signature error on
baseline (documented since Session 1). Both edits confirmed live inside the rebuilt+recreated api
container; `/health` ok. **Not yet done:** a real end-to-end message (would hit Groq) to visually
confirm "Hi Sayantini," + inbox "Sayantini Sarkar" — deferred to the next organic run to save quota.
Changes **uncommitted** (user: log now, commit later).

### Fresh start executed (2026-07-25) + Fix 58
**Fresh start done** (full wipe + real WhatsApp), following `docs/fresh-start-runbook.md`: wiped
`cx-data`/`neo4j-data`/`opensearch-data` (kept ollama/huggingface), rebuilt api (bakes Fixes 56, 57,
and the C-side of the name work — `/graph` route now returns `name`), brought up, 5 BFSI customers
auto-reseeded, KB re-indexed (9 docs). Verified all deps: 5 customers, empty inbox, ngrok up
(domain unchanged `tactical-dribble-booting…`, so Meta webhook needed no change), Groq key valid +
quota (one `max_tokens=1` probe), WhatsApp token valid. **Note:** the token used was still a
**temporary** token (expires 20:30 IST 25-Jul), not the recommended System User token — user chose to
proceed. **Ollama false-alarm caught:** `ollama list` empty after the wipe looked like a missing model,
but `OLLAMA_ENABLED=false` — the stack runs on **Groq**, so Ollama's empty volume is irrelevant and no
`ollama-pull` is needed (this is why prior fresh starts never needed it either).

**Two behaviours surfaced during post-reseed testing (diagnosed, see Fix 58 for the one fixed):**
1. **Vague follow-up mis-answered + mis-grouped (NOT fixed — pre-existing design limit):** a WhatsApp
   follow-up "Do I have any next steps before this due date?" was (a) answered with the PREVIOUS reply
   (health-policy due date) verbatim, and (b) classified `loan_status` instead of continuing
   `policy_status` — so Lineage split it into a separate LOAN STATUS group. **Root cause (traced in
   `groq_generator.classify_message`, ~L206-210):** the history passed to the classifier includes only
   `direction == "inbound"` turns (the customer's prior *questions*) — the AI's prior *answers* are
   excluded. So a follow-up referring to something the AI *said* ("this due date") can't be grounded →
   the model guesses the intent (wrong group) and reuses/misfires the answer. Answer-side cousin of the
   Session-7 ticket-continuity work; deferred.

### Fix 58 — WhatsApp offer 400 (bare number not in Meta allowed list)
**Symptom (user):** an approved offer showed as sent on Email + WhatsApp in Lineage, but the WhatsApp
one never reached her phone. **Diagnosed (live, authoritative):** api logs showed the offer's WhatsApp
send 400'd 3× on `graph.facebook.com/.../messages`. Reproduced the send to read Meta's actual error:
**`(#131030) Recipient phone number not in allowed list`** — NOT the token (token is valid; a test send
to `917890864700` returned HTTP 200 and delivered). Root: her record stores the number **two ways** —
`7890864700` (bare) and `917890864700` — and the send hit the **bare** one, which Meta rejects (needs
the country code). **Why normal replies were unaffected:** `delivery.send` sends a reply to
`message.channel_identifier` — the number the customer messaged *from*, which Meta always delivers with
the `91` prefix; only **bank-initiated** sends (offers) pick a stored identifier and can hit the bad
variant. The dedupe from Fix 53 correctly collapses the two to one send but keeps the **first**
(=bare) → 400. **Fix (Level 1, backend):** `_normalize_wa_recipient()` in
`services/channel_adapter/whatsapp_meta.py::send_outbound` — bare 10-digit → prepend `91`; already
`91…`/`+91…` → digits; empty/None passthrough. Placed in `send_outbound` so it covers offers, replies,
and held drafts. **Verified (no Groq):** normalizer table (bare→`91`, prefixed unchanged, `+91`
normalized, empty/None safe) all pass — an early `+91` edge case was caught by the test and fixed
BEFORE rebuild; fix confirmed baked into the rebuilt image; api healthy. **Not proven:** an actual
offer landing on her phone (needs triggering an offer = Groq + real send) — deferred to next organic
test. **Level 2 (root) still deferred:** normalize phone on write so duplicate rows never exist (Fix 53
territory; needs identity-path change + reseed). Two diagnostic test WhatsApp sends were delivered to
her real phone during diagnosis (the `91` ones, HTTP 200). Changes **uncommitted**.

### WhatsApp token — permanent(ish) fix installed (2026-07-25)
The recurring hours-long token expiry (3+ times this session) is resolved: a **SYSTEM_USER** token was
generated via business.facebook.com → System users ("Omnichannel_WhatsApp_Backend"), 60-day expiry,
scopes `whatsapp_business_messaging` + `whatsapp_business_management`. Verified in the running container
(`debug_token`: valid, `type: SYSTEM_USER`, **expires 2026-09-23** ~59 days). No more few-hour tokens —
**refresh before ~23 Sep 2026**. (A "Never" expiry option exists at the Set-expiry step if a
truly-permanent token is wanted later.) See memory [[whatsapp-token-expiry]].

---

## Session 9 — 2026-07-26

Branch: `Sayantini-phase2-ui-changes`. **Merged in a friend's (Digvijay's) analytics-page work** so
this branch holds both bodies of work with nothing lost.

### Merge — Digvijay's analytics-page work into `Sayantini-phase2-ui-changes`
**Goal (user):** combine this branch (Fixes 42–58) with Digvijay's branch, which adds work on the
admin Analytics page, **without losing any implementation from either side.**

**Which branch was his:** of all the remote branches, `origin/digvijay-work-branch` was the analytics
one — its tip is literally `eb55195 "Additions in analytics page"` (2026-07-22). This branch had
**forked off `digvijay-work-branch`** originally, so the two shared a clean common ancestor
(`5881715`, 2026-07-16); since then **this branch = 5 commits** (Fixes 42–58) and **his = 1 commit**
(`eb55195`).

**His commit (`eb55195`) — 6 files:** `apps/admin-ui/{app.js,index.html,style.css}` (the analytics
**LLM-usage panel** — `renderLlmUsagePanel`, `loadAnalytics` additions),
`services/observability_service/llm_usage.py`, `services/persistence_service/repository.py`, and a new
migration `services/persistence_service/migrations/010_llm_usage_model_version.sql`. The 3 shared UI
files were the only overlap risk; his edits sit in the analytics regions, away from this branch's edits.

**Method (safe, reversible, verified before acting):**
1. **Dry-run first** — `git merge-tree --write-tree HEAD origin/digvijay-work-branch` reported a
   **clean auto-merge, exit 0, zero conflicts** *before* touching anything.
2. **Backup tag** `backup-before-analytics-merge` → `a7da603` (instant undo:
   `git reset --hard backup-before-analytics-merge`).
3. **`git merge --no-ff origin/digvijay-work-branch`** → merge commit `f96cb5c`; all 4 shared files
   auto-merged, no conflicts. Both histories preserved (nothing rewritten/dropped).
4. **Verified both sides coexist:** his `renderLlmUsagePanel` / `loadAnalytics` / migration `010`
   present; this branch's Fix 58 (`_normalize_wa_recipient`), Fix 42 (offers UI), Fix 41
   (`statusLabel`), and the session log all intact; his `llm_usage.py` + `repository.py` byte-compile.
5. **Test suite (Groq-safe — `GROQ_API_KEY=""` so no accidental quota spend):** **137 passed, 5
   failed.** Proved the 5 failures are **pre-existing, not merge-caused** by running the same 5 on the
   pre-merge tree (via a throwaway `git worktree` at the backup tag) — **identical 5 failures**. Of the
   5: 3 are the long-documented `test_phase1` mock-signature failures (since Session 1); 2 are
   Groq-key-dependent and only surface because the key was deliberately blanked for quota safety. **0
   Groq tokens spent.**
6. **api rebuilt + recreated** off the merged tree so migration `010` applies (his change is backend +
   a migration; the analytics LLM-usage panel needs the baked image, not just the bind-mounted UI).

**Result:** `Sayantini-phase2-ui-changes` now contains **both** branches' work; ahead of origin by 2
(his commit + the merge commit). **Not pushed** (awaiting user go-ahead). Backup tag retained.

### Analytics page — whole-page creative redesign (frontend-only)
**User ask:** the Analytics page (KPI tiles, bars, tables, LLM panel) looked flat; make it creative,
one cohesive design system, matching the LLM-panel restraint (subtle gradient, not flashy).
**Design system (`apps/admin-ui/`):** introduced a shared **`.kpi-tile`** class (gradient wash + thin
top accent bar + small icon + hover lift) with per-tone variants (blue/pur/grn/amb/red/pnk) and a
shared `renderKpiTiles()` JS helper. Applied to: all 8 KPI tiles (Customer Care `renderOverview` +
Solution Performance `renderSolutionStats`) AND the LLM usage tiles (renamed the earlier `.llm-stat-*`
→ `.kpi-*` so there's ONE tile system, not two). Bars (`renderBars` + `.bar-*`): taller rounded track,
gradient fill (`color-mix` tint), row hover, bolder tabular values. Sentiment bar: bigger total,
rounded gradient segments, colour-keyed legend. Agent table: colour dot per team + right-aligned
tabular numerals (reused `.llm-op-*`). Chart cards: hover shadow. Frontend-only; live via bind mount;
asset versions bumped to `20260726-2/-3`. `node --check` OK. **Modern-browser caveat:** bar-fill tint
uses CSS `color-mix()` (all current browsers; graceful degrade to no-tint on old ones).

### Analytics — formula tooltips on every KPI card
**User ask (mid-task):** KPIs involve formulas; hovering a card should show the formula. **Fix:**
`renderKpiTiles` gained an optional `tip` field → native `title` tooltip on the whole tile + a small
`?` affordance (`.kpi-help`) so users know to hover. Wired a plain-English formula into all 8 tiles
(both sections). Native-tooltip pattern, consistent with the Profile Snapshot tiles.

### Analytics — Solution Performance section rebuilt with practical, data-backed KPIs
**Why:** the section's metrics were broken or meaningless on real data — **Escalation rate = 233%**
(bug: `total_escalated`(7 tickets) ÷ `total_conversations`(3) — mixed units, >100%), **Resolution
level mix** always "No data" (all `llm_usage_events.resolution_level` are NULL), **14-day trend** had
one day of data. User asked for KPIs that "practically make sense" on the data that exists.
**Escalation-rate definition (settled after a long clarification with the user — the key decision):**
NOT conversation-level (2/3 → saturates toward 100% as every customer eventually escalates) and NOT
ticket-level (7/7 → circular, since a ticket is mostly *created* on escalation). The honest denominator
is **total inbound customer queries** (every message the customer actually sent), so non-escalating
routine queries pull the rate down and it stays a real 0–100% rate:
**escalation rate = escalated tickets ÷ inbound turns = 7 ÷ 18 = 38.9%.**
**The 4 KPIs (all present-state, all compute today):** Escalation rate 38.9% · Avg risk score 60.0
(`AVG(priority_score)` over OPEN tickets) · Critical load 4 (open critical tickets) · Drafts handled 14
(`reply_drafts` status=sent — human-in-the-loop throughput). **The 2 charts** (replaced trend +
resolution-mix): **Open tickets by risk band** (priority_score bucketed Critical/High/Med/Low) and
**Why tickets escalate** (`escalation_reason` breakdown; raw codes prettified AND merged after
prettify so `assisted_resolution_required:transaction_dispute` + `:loan_status` count as one
"Assisted resolution" bar = 4, not two — a self-caught bug during verification).
**Files:** `services/analytics_service/metrics.py` (new `SolutionPerformanceMetrics` + `LabelCount`
dataclasses); `services/analytics_service/aggregator.py` (new `get_solution_performance` + `_risk_band`
+ `_pretty_reason`); `apps/api/routes/analytics.py` (new `GET /analytics/solution-performance`);
`apps/admin-ui/` (rewrote `renderSolutionStats(sp)`, new `renderSolutionCharts(sp)`, added the fetch to
`loadAnalytics`, repurposed the two chart containers to `riskBandPanel`/`escReasonPanel` with new
titles). The old `renderTrendPanel` + `renderResolutionLevelPanel` JS are now **orphaned dead code**
(no container targets them; left in place, flagged for cleanup). **Verified (0 Groq — pure SQL):** ran
the new aggregator against a copy of the real DB (38.9% / 60 / 4 / 14; bands + merged reasons correct);
api rebuilt + recreated; `GET /analytics/solution-performance` live returns the expected JSON;
`/health` ok; served assets carry the new code. `node --check` OK; backend byte-compiles.

### Analytics — "Tickets by channel" fake-channel bug fixed (backend)
**Bug (from the user's Image-1 question):** the chart showed `graph` and `portal` as channels and a
flat inflated "7" on every channel. **Root cause:** `get_channel_metrics` joined
`tickets → conversations → channel_identities` and grouped by `ci.channel` — so (a) it surfaced
internal identifier *types* (`graph`/`portal`) that are not contact channels, and (b) it counted each
ticket once **per identity the customer had**, inflating every channel to the same number.
**Fix (`services/analytics_service/aggregator.py`):** count each ticket ONCE on the channel it actually
arrived on — the channel of the turn(s) carrying its `ticket_id` (`MIN(ct.channel)` per ticket) — and
filter both ticket + message queries to non-empty channels. **Verified on real data (0 Groq):** now
only the 3 real channels (email 1 / web_chat 5 / whatsapp 1 tickets), no `graph`/`portal`, no inflation.

### LLM-panel version tag — config-hash `v-xxxx` implemented (backend)
**Design (user's earlier decisions):** version = fingerprint of OUR config (model + the sampling params
actually sent), "hash what's actually sent" so adding a param later makes a new version; short tag in
the table + full config logged so the tag is decodable.
**Impl:** `services/observability_service/llm_usage.py` — `_normalize_params(model, params)` (keeps only
params genuinely passed; None → passthrough so old call sites are unchanged) + `_config_version(cfg)`
(`v-` + first 4 hex of sha256 over the sorted config, deterministic). `record_llm_call` gained a
`params` kwarg → sets `model_version` from the config hash (falls back to the provider
`system_fingerprint` when no params) AND stores the full config in `metadata.model_config`
("log it somewhere"). `services/rag_service/groq_generator.py::_generate` passes `params={temperature:0.2}`
to all 3 record sites. `services/persistence_service/repository.py` — the `by_model` summary now samples
`metadata_json` per (model, version) group and decodes `model_config` so the panel can show the params
behind each tag. **Verified (0 Groq):** temp 0.2 → `v-1412`, temp 0.5 → `v-1df4`, +max_tokens → `v-942f`
(each change → new tag), deterministic, None-passthrough. **Note:** the existing 104 rows pre-date the
feature → they still read version `unknown`/`model_config` null (correct); only NEW LLM calls carry a
`v-xxxx` — visible after the next real message through the system (deferred to save Groq quota).

### Cleanup (D)
Removed the two orphaned dead render functions (`renderTrendPanel`, `renderResolutionLevelPanel`) and
the now-unused `/analytics/trend` fetch from `loadAnalytics`; re-indexed the Promise.all results
(solution-performance moved 8→7). Asset version `app.js?v=20260726-4`. `node --check` OK.

### Analytics — section headers restyled (accent bar + icon)
The three section labels (FinOps / Customer Care / Solution Performance) were plain 11px grey
uppercase text that read as captions, not structure. Restyled `.section-lbl` into a coloured
gradient left accent bar + an icon chip + a larger/bolder/darker label (13px/700), colour-coded
per section (FinOps green 💰, Customer Care blue 🎧, Solution Performance amber ⚡). Heading-only
(no description line, per user). Frontend-only (`apps/admin-ui/index.html` + `style.css`,
`style.css?v=20260726-4`); `.section-lbl` is used only on these three headers (verified). Live via
bind mount, reload only.

### Analytics — LLM observability panels reworked (per user review)
Several rounds of iteration on the FinOps LLM section:
- **Operations table:** Calls, Token share, Cost AND Avg latency each now render as their own meter
  bar (bar + value), each scaled to that column's max, coloured by the operation. (Fixed a layout
  bug where `display:flex` on the `<td>` broke table columns — the flex row moved to an inner
  `.llm-meter-wrap` so the cells keep their columns.)
- **Cost/Latency by model-version tables → comparison strips:** one bar row per model+version,
  **normalized PER CALL** (cost = total÷calls; latency already avg) so versions with different call
  counts compare fairly instead of a volume race. Same bar colour for every row (the metric is the
  same; version identity is carried by the tag chip, not bar colour). Label = model name + the
  version tag as an inline chip, with the human-readable config on the line below (no more
  duplicated version stacked above its own hash). Card titles state the basis: "Avg cost per call —
  by model / version" / "Avg latency per call — …".
- **Usage-over-time line charts (new):** two side-by-side hourly line charts (Cost | Tokens), one
  coloured line per model+version, shared X-axis + colour legend. Backend adds a `time_series` block
  to the observability summary (hourly × model × version). Rewrote the renderer: large viewBox (true
  small axis fonts), gradient area fill, soft dashed grid, a JS crosshair + tooltip (native `<title>`
  was unreliable) showing every series' value at the hovered hour. **Timezone bug fixed:**
  `created_at` is stored UTC; the SQL now buckets by **IST (+5:30)** and the axis is labelled
  "Time (IST)" (India-only deployment, same assumption as the WhatsApp `+91` normalization).
- **Removed the Customer sentiment card;** the remaining three (Tickets by channel · Top intent
  trends · Agent/team performance) now sit side by side in one row. `renderSentimentPanel` guarded
  for the missing container.
- A granularity selector (hourly/daily/weekly/monthly/quarterly) was discussed and **deferred** (data
  is currently one day; coarse grains need per-grain time ranges — noted for later).

### Tests + commits
New `tests/test_analytics_observability.py` (8 tests, 0 Groq): version-tag changes/determinism/None,
escalation denominator = inbound turns, reason-merge, and channels-exclude-fake. Full suite:
**145 pass, 5 pre-existing `test_phase1` failures** (identical set proven pre-existing). The redesign +
KPI work was committed as `36f0d4c`; the channel fix + version feature + cleanup + tests as a follow-up
commit. api rebuilt + recreated for all backend changes; endpoints verified live. **Not pushed** yet.
