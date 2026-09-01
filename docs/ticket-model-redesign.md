# Ticket model redesign — analysis and plan

**Proposal (user's):** every customer query gets a ticket id. The existing rules keep deciding
the *hold*. A ticket starts as a **logging id**, and becomes **serviceable** the moment something
in that thread needs a human. Grouping is by *matter*, not by intent label; a genuine topic change
gets a new id and the reply says so.

**Goal.** A customer's history should read as a set of **named matters** — "health claim dispute",
"card late fee", "failed transfer" — each carrying its own exchanges across every channel, instead
of a flat wall of disconnected boxes. The system already *has* this continuity (the graph links
messages to cases; `get_open_cases` feeds them to the reply). The screen cannot show it, so the
product looks like it has no memory when it does. **This redesign exists to make that memory
visible.** Success is judged on screen — see Phase 6, not the unit tests.

**Root cause in one line.** The system had no name for a *topic*. It named customers, conversations
and messages, but the only relatedness assertion it ever made was `ticket_id` — and that appeared
only when a human was needed. This gives a topic a name that always exists.

Everything below was measured against the live system on 2026-09-01. Phases 0–2 are built;
3 onward are not.

---

## 1. What is broken today

**One boolean does two jobs.** `ticket_decision.required` decides *both* whether a ticket exists
**and** whether a human reviews the reply. `review_gate.py` says so explicitly: *"HOLD the reply
if and only if `ticket_decision.required` is True."*

So there is no way to express *"this is a thread, but no human is needed"* — which is the
overwhelmingly common case. Q1 (*"why was my claim rejected?"*) needed a thread id and no human,
and the system had no vocabulary for it.

**Consequence — the UI cannot group anything unticketed.** `buildUnits` (app.js) keys a request on
`ticket_id`:

```js
var key = it.ticket;
if (key && byKey[key]) { merge } else { new box }
```

A null key can never take the merge branch. There is **no fallback** — no conversation threading,
no intent grouping, no time window. Every unticketed exchange renders as disconnected boxes,
however obviously related.

**And the same-matter judgement is not the problem.** It already exists and is well built.

---

## 2. The referee — what is already there

`TicketManager._referee_match` asks an LLM: *does this message continue one of these open tickets,
or is it a new matter?*

**It is better designed than I expected:**

- Reads the **message text**, each candidate's description, **and the actual messages on that
  ticket** from the graph (`get_case_messages`, Fix 73) — not just how the ticket opened
- Candidates are **deliberately not filtered by intent**. The code comment gives the reason:
  *"any update on my dispute?"* classifies as `ticket_status`, so an intent filter would exclude
  the dispute ticket it is obviously about. *"Relatedness is a judgement about the text — not
  about two intent labels being equal."* **That is exactly the requirement.**
- **Safe by construction:** the LLM may only pick from a code-vetted candidate list. Any doubt,
  parse miss, or LLM failure returns NEW. A spurious fork is visible and fixable; a spurious merge
  corrupts the record silently.

**Measured:**

| | |
|---|---|
| Calls | 61 |
| Real failures | **0** (18 "failures" were my own test runs with the key blanked) |
| Avg cost | **673 tokens** |
| Times it attached to an existing ticket | **1** |

**The 1-in-43 attach rate is NOT evidence it is broken.** It is a consequence of when it runs:

```python
ticket_scope = _ticket_scope(intent, text, escalation_reason, graph_context)
if not escalation_reason:
    return None          # <- no scope
...
if not existing and ticket_scope:   # <- referee only runs when scope is non-null
```

The referee is gated behind `ticket_scope`, which is `None` unless the message escalated. So today
it only ever sees escalated messages, which are rare — and most of those genuinely were new matters
(the ticket list shows different intents, not duplicates of one).

**The one real duplicate** — two `account_balance_inquiry` tickets on one conversation — was
created by the now-deleted Rule 9, not by a referee misjudgement.

**Session 21's "20% accurate" figure is not a reliable basis for a decision.** It was one case.
Before making the referee the backbone of all grouping, its accuracy needs measuring on a real set
of message pairs — see Phase 0.

---

## 3. The proposed model

| Concept | Today | Proposed |
|---|---|---|
| Ticket exists | only when a human is needed | **always** — one per matter |
| Human holds the reply | `required == True` | **unchanged** — same rules |
| Ticket status | open / closed | **logged** -> open (serviceable) -> closed |
| Grouping key | `ticket_id` (usually null) | `ticket_id` (**always present**) |
| Same-matter decision | referee, rarely reached | referee, on every message |

A ticket becomes **serviceable** the first time any message in that thread triggers a hold. Before
that it is a logging id: a stable name for "this matter", nothing more.

---

## 4. Pros

**It fixes the UI grouping at the root.** The UI groups by ticket because that is the only
relatedness assertion in the system. Making that assertion always exist makes grouping work
everywhere, with **no change to `buildUnits` at all**. No heuristic, no time window, no proxy.

**It separates two decisions that were never the same question.** "Is this a distinct matter?" and
"does a human need to see this?" are independent. Conflating them is why Q1 had no thread id.

**Every conversation gains a spine.** Today a customer's history is a flat list of turns. After
this, it is a set of named matters — which is what an agent actually needs, and what the Lineage
view was built to show.

**The customer gets a reference when there is something to follow up.** Once a thread becomes
serviceable it has a stable id the customer can quote on any channel. A logging id stays internal
(see 5.5).

**"This looks like a different issue"** in the reply, when a new thread starts, is genuinely good
service — it is what a human agent says.

**The machinery already exists.** The referee is written, tested, safe-by-default and already
intent-agnostic. This is mostly *calling it more often*, not building it.

---

## 5. Cons and risks — the honest list

### 5.1 Cost: an LLM call on every message
The referee averages **673 tokens**. A message already costs **~6,400** across 4-5 calls
(intent, answer, resolution level, case summary, customer context). Adding the referee to every
message is **~+10%**.

Against a **200,000/day** cap that is ~30 messages/day today, ~28 after. **The cap is the binding
constraint, not this change** — but it makes the existing waste matter more (see 5.6).

### 5.2 The referee's accuracy is unproven at this volume
It has attached **once**. Running it on every message multiplies both its value and its errors.

- **A wrong NEW** (fork) — visible, recoverable, and the current safe default.
- **A wrong MATCH** (merge) — silently files a new problem under an old thread. This is the
  dangerous direction, and the failure mode the referee's own comments say it was built to avoid.

**This must be measured before building.** See Phase 0.

### 5.3 Ticket volume rises sharply
Every query becomes a ticket. On the live data that is ~10 tickets -> ~40+. Affects:

| Surface | Impact |
|---|---|
| **Analytics** | Every ticket count changes meaning. "Escalation rate" (escalated ÷ inbound) still works; raw counts do not |
| **Right panel "Open Tickets"** | Must show serviceable only, or it fills with logging ids |
| **Jira sync** | Logging tickets are **not** synced (decided). Implement as a filter at the sync boundary, not by withholding data - the id stays in our store so a logging/monitoring system can pick it up later |
| **`get_open_cases`** (graph) | Feeds the reply prompt. Capped at 5 — logging tickets would crowd out real cases and reintroduce the false *"already logged under"* claim (Fix 119) |

**5.3 is the largest hidden cost. It is not a code change, it is a meaning change across every
surface that counts tickets.**

### 5.4 A third status is a migration
`TicketStatus` is an enum with a stored value. Session 22's Fix 109 renamed `resolved` -> `closed`
and needed migration `016` plus updates to 8 JS sites and the analytics SQL. Adding `logged` is the
same shape of work. The lesson from that fix — *"every site that accepted BOTH words now accepts
one"* — applies: a status nothing rejects is a status that drifts.

### 5.5 (Settled, not a risk) The customer only sees serviceable references
A logging id is **internal**. The reference is quoted to the customer only once the ticket becomes
serviceable — which is precisely when there is something for them to follow up on. A reference on
every routine question would read as bureaucratic and invite *"what happened to TKT-x?"* about a
question that was answered instantly.

### 5.6 It exposes existing waste
Measured per operation:

| Operation | Calls | Avg tokens |
|---|---|---|
| `customer_context` | 8 | **3,331** |
| `answer_generation` | 45 | 2,329 |
| `intent_classification` | 35 | 2,045 |
| `case_summary` | **57** | 1,383 |
| `opportunity_generation` | **48** | 909 |
| `ticket_referee` | 43 | 673 |
| `ticket_action_detection` | **95** | 198 |

`case_summary` (57) and `opportunity_generation` (48) fire **more often than
`answer_generation` (45)**. Both are agent-panel features running on the customer message path.
Moving them off it would free ~35% — far more than the referee costs.

### 5.7 Risk of re-breaking what was fixed today
Fixes 117, 118, 120, 123 all narrowed *when* tickets are created. This widens it. The specific
regressions to guard:

- Fix 117: a graph-answered question must still **auto-send** (ticket, but no hold)
- Fix 123: `approval_required` must still hold
- Fix 119: a logging ticket must not be quoted to the customer as *"already logged under"*

### 5.8 The candidate set is bounded in a way this design breaks
**Found by the user asking "for how long history will it try to match?"** — a gap in the first
version of this plan.

Today's bounds, all deliberate:

| Bound | Value |
|---|---|
| Candidate tickets offered to the referee | **5** most recent |
| Messages shown per candidate | **4** newest |
| Text per item | 300 chars description, 160 per message |

The candidate query is:

```sql
WHERE conversation_id = ? AND status != 'closed' ORDER BY created_at DESC LIMIT 5
```

**`status != 'closed'` is doing the real filtering today**, because tickets only exist when
something escalated and they get closed. Under this design, logging tickets accumulate with **no
natural close event** — nobody resolves *"what is my card limit?"*. Five routine questions would
fill all five slots and **push a live dispute out of view**, so the referee could not match a
follow-up to it. That is the same failure the intent filter used to cause (see §2).

**A proposal of mine was tested and withdrawn.** I suggested ranking by `updated_at` ("last
touched"). Two things, both **measured**:

1. **`updated_at` does not mean last touched.** `create_or_get_ticket` ends `if existing: return
   existing` — attaching a message never calls `update_ticket`. Proven on ticket `7f590b`:
   `updated_at` = 13:11:19, with a message attached at **13:11:49** that did not move it. The field
   tracks *administrative* changes (created, scope refined, referee attached, status updated).
2. **Repurposing it would corrupt analytics by an order of magnitude.** Three readers assume
   `updated_at` = close time — avg resolution, per-team average, and closed-per-day. Measured on
   live data: average resolution time would report **18.3 minutes instead of 394.2** — a 21x change
   on a headline demo metric. Ticket `33e42f` alone: 1,867 minutes -> 50.

**The fix is a separate field, not a repurposed one:** `last_activity_at`, bumped when a message
attaches. `updated_at` keeps its meaning, analytics is untouched, and the referee gets a field that
says what it needs.

```sql
WHERE conversation_id = ? AND status != 'closed'
ORDER BY COALESCE(last_activity_at, created_at) DESC LIMIT 5
```

Plus a **two-tier guarantee**: serviceable tickets always get a slot, so a live case can never be
crowded out by routine chatter.

*Also noticed, pre-existing and unrelated:* the per-team query (aggregator.py:343) has **no status
filter**, so it already averages `updated_at - created_at` over open tickets, where that difference
is meaningless.

---

### 5.9 The two status vocabularies cannot both be satisfied
**Raised by the user as the blocker on Phase 2; verified in code 2026-09-01.**

| Side | Question it asks | Sites | Effect of `logged` |
|---|---|---|---|
| Backend SQL | `status != 'closed'` | 10 | counted as **open** |
| Neo4j Cypher | `t.status <> 'closed'` | 1 (`get_open_cases`) | counted as **open** |
| Frontend JS | `status === 'open'` / `'in_progress'` | 10 | counted as **nothing** |

The two directions are asymmetric, and that is the whole problem: SQL **admits** the new word,
JS **drops** it. A logging ticket would be **invisible to the agent and authoritative to the
LLM** — Fix 119's false *"already logged under"*, but now on a ticket no screen can show and no
agent can close.

*Correction to this document's earlier count:* it said 9 SQL sites. There are **10** on the
`!= 'closed'` side, plus **7** on the positive `= 'closed'` side it did not count.
`aggregator.py:30-31` builds `open_cnt` and `resolved_cnt` from that pair, so every logging ticket
would inflate the headline open-case number.

### 5.10 Deleting a ticket row does not delete its graph node
**Found by measuring whether the two stores agree, before building Phase 2. They do not.**

| Store | Tickets |
|---|---|
| SQLite | 10 |
| Neo4j | **11** |

`tkt_b6e0598f02a4` (`claim_status`, `open`, Sayantini) exists **only in the graph**.
`get_open_cases` reads the **graph**, so its own query returns **two** open claim cases for a
customer who has one — and the ghost sorts first. The trusted account context handed to the reply
generator asserts a case that exists nowhere else.

**Not an application delete:** there is no `DELETE FROM tickets` or `delete_ticket` in the
codebase. `PRAGMA foreign_key_check` reports **12 violations** (6 `ticket_events`, 6
`retrieval_evidence`). Since `ticket_events.ticket_id` is a foreign key and
`PRAGMA foreign_keys = ON`, those events could only be written while the ticket row existed — so
rows were removed afterwards, consistent with manual data cleanup, and the graph node was never
removed with them.

**3 of 13 attempted tickets are orphaned**, including `tkt_451e7ce71a63` from Fix 122.

**The creation path is NOT at fault — measured.** All three orphans logged
`ticket_created` **and then** `crm_sync_failed`, and `sync_ticket` re-reads the row before it can
write that second event. So the row existed and the write succeeded. Better: **every one of the 10
surviving tickets carries the same `crm_sync_failed` event** (the Jira 400), so orphans and
survivors are *indistinguishable* by what the application did. Nothing about creation separates
them.

**What is actually missing is a delete path.** Rows were removed by manual cleanup, and:

| Gap | Consequence |
|---|---|
| No `delete_ticket` in the codebase | Cleanup is done by hand against SQLite |
| No `ON DELETE CASCADE` on `ticket_events` / `retrieval_evidence` | 12 FK violations left behind |
| Nothing deletes the Neo4j node | The graph copy survives its own row — the ghost |

The three writes *are* unsynchronised (`create_ticket`, `add_ticket_event`, and
`upsert_ticket_node` in `graph.py:842`), and that remains a latent risk worth fixing. But it is
**not** what produced these orphans, and no evidence in this database shows a failed write ever
leaving a ghost.

**Why it still matters for this design.** Not because creation is lossy — it is not. Because
**the graph is the store the reply prompt reads**, and it currently has no way to lose a ticket
that SQLite has lost. Under Phase 4 every routine question becomes a ticket, so the volume of rows
that a future cleanup would have to remove — from *two* stores, in step — rises ~4x. A delete path
that maintains both stores is the precondition; atomic creation is a separate, lesser concern.

*A correlation that was tested and withdrawn:* the ghost logs `crm_sync_failed` (Jira 400) one
second after creation, which looked causal. `sync_ticket` catches that failure, records it as
`crm_sync_status`, and returns normally. **Jira is unrelated.**

*Also withdrawn:* carrying serviceability as a flag in `tickets.metadata_json` instead of a third
status. The column exists (migration 002) and already holds `ticket_scope`, but the graph does
**not** mirror it — `upsert_ticket_node` takes an explicit parameter list, and `ticket_scope` was
promoted to its own node property when the graph needed it. A flag would need a new parameter, a
new `SET t.serviceable`, all three call sites updated, and would leave **two** fields to sync
across two stores instead of one. `logged` on the status is the better choice; 5.4 wins.

## 6. Plan

### Phase 0 — Measure the referee — **DONE, PASSED 10/10**
Ten hand-labelled cases replayed through `_referee_match` on 2026-09-01.

| Case | Expected | Got |
|---|---|---|
| "Any update on my dispute request?" | match dispute | match |
| "The Rs.5,776 to Samarth Thaker still has not reached him." | match dispute | match |
| "I want to dispute **another** charge - my gym billed me twice." | NEW | NEW |
| "When is my next insurance premium due?" | NEW | NEW |
| "That does not make sense... I need this claim honoured." | match claim | match |
| "What about my **other** claim CLM001003?" | NEW | NEW |
| "Can I pay just the minimum on that late fee?" | match card | match |
| 3 open: "Any update on the transfer to Samarth Thaker?" | match dispute | match |
| 3 open: "How do I open a new savings account?" | NEW | NEW |
| 3 open: "I still want that rejected claim reconsidered." | match claim | match |

**10/10 correct. Zero wrong merges** — the dangerous direction. It separated *"another charge"* from
the open dispute and *"my other claim"* from the open claim, which is exactly the discrimination
this design needs. **Gate passed.** Cost ~640 tokens per call.

**My first harness was broken and nearly produced a false finding.** It returned NEW on all ten and
I was about to conclude the referee could not match at all. The cause was mine: I passed
`repository=None`, and after a *correct* match the code calls `repository.add_ticket_event(...)`,
which raised `AttributeError` into the function's bare `except Exception: return None` — turning
every right answer into NEW. Caught only because the raw LLM output said `tkt_dispute01` while the
function returned NEW. **~6,400 tokens wasted re-running it.**

**A real finding falls out of that:** `_referee_match` wraps everything in `except Exception: return
None`, so a **database failure while attaching silently becomes a forked ticket**, with nothing
logged. Safe-by-default, but invisible — worth narrowing the except or logging the swallow.

### Phase 1 — Separate the two decisions — **DONE**
`TicketDecision` gains `hold_required`, which **defaults to `required`** via `model_post_init`.
`review_gate.py` now reads `hold_required` instead of `required`, with a fallback for callers and
test stubs that do not carry the field.

**Verified behaviour-neutral:** `required=True -> hold=True`, `required=False -> hold=False`,
a plain stub without the field still holds, `None` still does not. And the two can now **diverge**,
which is what Phase 4 needs: `required=True, hold_required=False` produces a ticket with **no hold**
— a logging id, auto-sent. Tests 5 failed / 147 passed, the documented baseline.

### Phase 1.5 — Give tickets a delete path that maintains both stores — **NEW (see 5.10)**
There is no `delete_ticket`, no FK cascade, and nothing removes the Neo4j node — so the manual
cleanup this project actually does leaves orphaned children and ghost graph nodes. Provide one
deletion routine that removes row, children and graph node together, and reconcile the existing
drift (1 ghost node, 12 FK violations).

**Not blocking Phase 2 on the evidence available.** Creation was measured and is not lossy: all
13 tickets, orphaned and surviving alike, completed the same write sequence. This phase is about
*cleanup*, which Phase 4 makes ~4x more voluminous — not about a broken write.

### Phase 2 — Add the `logged` status — **DONE (readers only)**
Enum value + migration + every read site. Follow Fix 109's method: make every site accept exactly
one word, so a wrong value is visible immediately rather than silently tolerated.

**Built 2026-09-01 as two named inclusion lists rather than by auditing sites**, because
`!= 'closed'` is defined by *exclusion* and cannot reject a new value (5.9):

- `SERVICEABLE_TICKET_STATUSES` = open, in_progress — a human is involved
- `ACTIVE_TICKET_STATUSES` = logged, open, in_progress — not finished

All 21 read sites now declare which they mean: 7 SQL, 1 Cypher (`get_open_cases`), 3 analytics,
10 JS. `_allTickets` gained a third bucket behind an `allTickets()` accessor, since eight callers
did `concat(open, closed)` and would have dropped `logged` silently. Migration 017 records the
vocabulary change; `tickets.status` is free TEXT so no schema change was needed.

**Readers only — nothing writes `logged` yet.** That is Phase 4, and it must not land before
Phase 3 and 3.5.

**Verified** with 9 assertions on a throwaway DB, zero Groq calls: logged is included in all five
continuity lookups, excluded from the customer/agent panel, and counted as neither open nor
resolved. Suite unchanged against baseline — note the recorded "5 failed / 147 passed" baseline is
itself flaky (`test_distinct_l3_fraud_incidents_create_distinct_tickets` gives 5 or 6 on a clean
tree).

**Still open, not a blocker:** tickets have no delete path that maintains the graph (5.10).

### Phase 3 — Guard the surfaces (before opening the tap) — **DONE**
**Re-scoped 2026-09-01 after checking the code: three of the four items were already delivered by
Phase 2.** Verified, not assumed:

| Item | State | Evidence |
|---|---|---|
| `get_open_cases` excludes `logged` | **DONE** | `queries.py`: `WHERE t.status IN ['open','in_progress']` |
| Right panel / agent surfaces show serviceable only | **DONE** | `find_open_tickets_for_customer` uses SERVICEABLE; its 2 callers are `routes/conversations.py:69` and `graph.py:405` (the reply pipeline's `_load_context`), so both the panel AND the prompt are covered |
| Analytics `open_cnt` / `resolved_cnt` / `sla_breach_cnt` | **DONE** | `aggregator.py:30-45`, inclusion lists |
| **Jira sync skips `logged`** | **TO DO** | see below |

**The one real item.** `create_or_get_ticket` calls `sync_ticket` on **every** ticket it creates
(`ticket_manager.py:124`). After Phase 4 that means *"what is my card limit?"* POSTs a Jira issue,
and the project fills with issues for questions that were answered instantly — ~10 tickets becomes
~40+. Decision 2 already settled the behaviour; this implements it as a filter **at the sync
boundary**, so the id still exists in our store for a future logging/monitoring system to read.

**Found while re-scoping — a fifth item the plan had not listed.** `get_agent_metrics`
(`aggregator.py:352-357`) has **no status filter at all**: it groups every ticket by
`assigned_team` and reports `COUNT(*)` as "handled" plus `AVG(updated_at - created_at)` as average
handle time. 5.8 noted the missing filter as pre-existing and unrelated — that judgement is
correct today but **stops being correct at Phase 4**, when every routine question becomes a row in
that count. "Handled" would silently come to mean "messages received", on a dashboard metric.
Add the SERVICEABLE (or CLOSED, for handle time) filter here in the same pass.

### Phase 3.5 — Bound the candidate set (before opening the tap) — **DONE**
Migration **018** adds `last_activity_at` (NULL default — NULL means "no message has attached",
and readers use `COALESCE(last_activity_at, created_at)` so an untouched ticket keeps exactly its
old ordering; backfilling `created_at` would assert an activity that never happened).

**A new repository method, not `update_ticket`.** `touch_ticket_activity` writes that one column
and nothing else. `update_ticket` sets `updated_at` on every call, and `updated_at` is the field
5.8 measured as unsafe to move — routing the bump through it would have reproduced the 21x
analytics error the separate column exists to avoid.

It is called at `create_or_get_ticket`'s `if existing: return existing` — the exact line where the
old model lost the fact, so a ticket could take messages for days with every timestamp frozen at
creation.

**Two-tier candidate query.** Serviceable tickets are taken first and the remaining slots filled
with the most recently active of the rest, so a thread a human is on can never be crowded out by
routine chatter.

**Verified 15/15, zero Groq calls**, including the failure this phase exists to prevent,
reproduced: one dispute opened first, then five newer routine questions.

| Query | Candidates returned |
|---|---|
| **Old** (`ORDER BY created_at`) | 5 routine tickets — **the dispute is absent** |
| **New** | dispute **first**, then the 4 most recently active |

Also verified: `touch` does not move `updated_at`; a touched logging thread outranks newer
untouched ones; the 5-candidate bound still holds. Migration tested against a **copy of the live
database** — 10 rows preserved, all NULL. Suite unchanged at 5 failed / 147 passed.

### Phase 4 — Create a ticket for every query — **DONE (code); UI unverified until 4.5/6**
`decide()` now returns `required=True` always and `hold_required = reason is not None`. The
escalation rules are **completely unchanged** — they simply answer a different question now.
Status follows the hold: no hold → `LOGGED`, hold → `OPEN`. An existing logging thread is
**promoted** to `open` the first time a message on it needs a person (one-way; only closing
ends a case), which also releases it to Jira.

**Two things this phase broke that the plan had not predicted — both the SAME conflation
surviving elsewhere, and neither would have been caught without running it:**

1. **`_ticket_scope` began `if not escalation_reason: return None`.** Sensible when tickets only
   existed on escalation; under Phase 4 it left the *majority* of tickets with a NULL scope — and
   three things are gated on scope: `find_active_ticket_for_scope`, the `:other` refinement path,
   and **the referee itself** (`if not existing and ticket_scope`). Every follow-up would have
   forked a new ticket: the exact failure this redesign exists to remove, reintroduced by the fix
   for it. Relatedness is a property of the text, not of whether a human was needed, so the scope
   is now computed for every message.
2. **`workflow_status` read `"human_follow_up" if state.ticket`** — conflating "a ticket exists"
   with "a person is involved", which is precisely what Phase 1 split apart. Every routine question
   would have reported `human_follow_up` while being auto-sent. Now reads `state.held_for_review`.

**Verified 17/17, zero Groq calls, zero network** — including all three 5.7 regressions:
Fix 117 (a graph-answered question has a ticket and is still auto-sent), Fix 123 (an approval
escalation still holds), Fix 119 (a logging ticket is absent from customer-facing open cases,
with an OPEN one present as the control). Also verified: promotion reuses the same ticket rather
than forking, is recorded as a `ticket_promoted` event, and releases the ticket to Jira.

**Two tests were updated, not "fixed" — they encoded the old model.** One asserted a routine
question SKIPS ticket creation; the other asserted `ticket_id is None` for a never-escalate
intent. Both now assert the new contract: a ticket exists, its status is `logged`, and the reply
is auto-sent. Suite back to the 5 failed / 147 passed baseline, same five tests.

**Not yet observed on screen.** Phases 4.5 and 6 are what close that — the 61 existing turns
predate this and can never be grouped.

### Phase 4.5 — Fresh start, because the existing data cannot show the result
**Added 2026-09-01. The plan had no step between "Phase 4 is built" and "it works", and that gap
is real, not procedural.**

Phase 4 changes what a ticket *means* from the moment it lands. It does **not** backfill. Every one
of the **61 conversation turns** now in the database was written under the old model, where a ticket
existed only if a human was needed — so those turns have `ticket_id = NULL` and always will.

Open the UI against that data after Phase 4 and a single conversation renders as **old turns still
in disconnected boxes, new turns grouped into matters, interleaved**. That is
indistinguishable from a half-working feature, and it is not a state anything can be judged from.

A wipe is therefore not tidying-up after the work — it is **the only way to observe whether the work
succeeded**. `docs/fresh-start-runbook.md` is written and verified for exactly this.

It also clears, in one step and without bespoke surgery, the drift 5.10 documents: the ghost graph
node, the 12 FK violations, 13 stale reply drafts. A targeted delete of the ghost was considered and
**dropped** — it treats one symptom on data that is about to be discarded.

**Known cost, decided knowingly:** the wipe destroys the **17 ResolutionMemory nodes**, some marked
`verified: True` by a human agent. They are the RL learning loop and are rebuilt by re-running the
demo, but they are not free.

**Order matters: wipe AFTER Phase 4 lands**, so the fresh data is produced by the finished system
rather than a half-migrated one.

### Phase 6 — Acceptance: look at the screen
**The plan's own purpose (§4: "It fixes the UI grouping at the root") was never stated as a
checkable outcome.** Every phase above is verified by unit assertions, DB reads and token counts —
none of which can tell you the screen changed. This phase closes that.

Run `docs/demo-question-set.md` (3 sequenced runs, every question already verified against real
records) and check its own stated criteria, which are the right ones:

| Must be true on screen | Proves |
|---|---|
| **Lineage: each thread is ONE row** with its exchanges as dots — not one row per message | grouping works |
| **Detailed: ticket A is ONE request** containing its steps, even though two other threads happened in between | grouping survives interleaving |
| An *"Any update on…"* step (a **different intent** from its ticket) lands on the right thread | the referee matches on meaning, not labels |
| An *"I also want to dispute…"* step opens a **separate** ticket | it forks rather than merges — the dangerous direction |
| *"Do I have anything pending?"* names the open cases with no reference given | continuity is real, not staged |
| A routine question is answered with **no ticket reference quoted** to the customer | decision 1 held: logging ids stay internal |

**If these do not hold, Phase 4 is not done** — regardless of what the unit tests say.

### Phase 5 — Topic-change acknowledgement — *optional polish*
When the referee answers NEW and an open thread exists, the reply notes it is a separate
matter. Genuinely good service (§4), but the grouping goal is met without it — do it only
if time allows after Phase 6 passes.


---

## 7. Recommendation

**The design is right.** It fixes the UI grouping at its root rather than with a proxy, and it
separates two decisions that were never the same question.

**Phase 0 is done and passed 10/10**, so the design is unblocked. The referee can tell same-matter
from new-matter, with zero wrong merges on the cases that matter.

**The one blocker on Phase 2 is 5.9 (the two status vocabularies).** 5.10 is a real gap in the delete path but does not block it.

**Phases 1 to 3.5 need no LLM calls** — code, migration and query work, verifiable with mocks and DB
reads. Only Phase 4's end-to-end test costs tokens.

**Phase 3.5 is not optional.** Without it, Phase 4 silently degrades the referee by starving it of
the right candidates, and the symptom looks like an LLM accuracy problem rather than a query bound.

**Phase 2 was the real work** — the meaning change across analytics, the prompt and the panel. It
is done, and it absorbed most of what Phase 3 was written to do (see the re-scope there). What
remains before the tap opens is small: the Jira filter, the `get_agent_metrics` filter, and
Phase 3.5's new field. Phase 4 itself is a few lines.

**Phases 2, 3 and 3.5 are inert on their own.** They change nothing anyone can see. That is by
design — they exist to make Phase 4 safe — but it means progress through them is not progress
toward the goal in any observable sense. **Phase 4 is the change**; everything before it is its
precondition, and everything after it is checking that it worked.

**Remaining order: 3 → 3.5 → 4 → 4.5 → 6**, then 5 if time allows. Phases 3 and 3.5 are best done
as one block, since neither is separately observable.

**5.6 is a decision, not a footnote — promoted 2026-09-01.** `case_summary` (57 calls) and
`opportunity_generation` (48) fire more often than `answer_generation` (45) and are agent-panel
features sitting on the customer message path. Moving them off it frees ~35% of per-message
tokens — the largest single lever in this document, larger than the referee costs. Against a
200,000/day cap on a demo that must be rehearsed, that is the difference between ~28 and ~40
messages a day. Independent of this redesign; worth doing before the rehearsals, not after.

---

## 8. Decisions taken

1. **The customer sees a reference only when the ticket is serviceable.** A logging id is internal.
2. **Logging tickets are never synced to Jira** — a filter at the sync boundary. The record stays in
   our store so a future logging/monitoring system can read it.
3. **Phase 0 is the gate.** Measure the referee before anything else is built.
