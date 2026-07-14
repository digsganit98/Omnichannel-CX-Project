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
