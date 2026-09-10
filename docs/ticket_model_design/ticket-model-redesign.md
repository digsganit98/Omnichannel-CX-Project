# Ticket model — design rationale

**Status: built and shipped.** Every phase of this redesign is in the code. This document is
retained as the record of *why* the ticket model works the way it does — the analysis below
explains decisions that the code cannot: why there is a `logged` status, why serviceability is
a status rather than a metadata flag, why `updated_at` could not be reused for activity
ordering, and why grouping is refereed by meaning rather than by intent label.

The phase-by-phase implementation plan has been removed now that the work is complete. The
per-fix history lives in `docs/Sayantini-session-changes-log.md`.

**The model.** Every customer query gets a ticket id. A ticket starts as a **logging id** and
becomes **serviceable** the moment something in that thread needs a human. Grouping is by
*matter*, not by intent label; a genuine topic change gets a new id.

**Goal.** A customer's history reads as a set of named matters — "health claim dispute", "card
late fee", "failed transfer" — each carrying its own exchanges across every channel, instead of
a flat wall of disconnected boxes.

**Root cause it addressed.** The system had no name for a *topic*. It named customers,
conversations and messages, but the only relatedness assertion it ever made was `ticket_id` —
and that appeared only when a human was needed.

Measurements below were taken against the live system on 2026-09-01.

---

## 1. What was broken

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
of message pairs. It was: ten hand-labelled cases were replayed through `_referee_match`, scoring **10/10 with zero wrong merges** — the dangerous direction.

---

## 3. The model

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

## 5. Risks considered, and how they were resolved

### 5.1 Cost: an LLM call on every message
The referee averages **673 tokens**. A message already costs **~6,400** across 4-5 calls
(intent, answer, resolution level, case summary, customer context). Adding the referee to every
message is **~+10%**.

Against a **200,000/day** cap that is ~30 messages/day today, ~28 after. **The cap is the binding
constraint, not this change** — but it makes the existing waste matter more (see 5.6).

### 5.2 The referee's accuracy at this volume
It has attached **once**. Running it on every message multiplies both its value and its errors.

- **A wrong NEW** (fork) — visible, recoverable, and the current safe default.
- **A wrong MATCH** (merge) — silently files a new problem under an old thread. This is the
  dangerous direction, and the failure mode the referee's own comments say it was built to avoid.

**This was measured before building** — 10/10 on hand-labelled cases, zero wrong merges.

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

### 5.7 Regressions guarded against
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
**Raised by the user as the blocker on the new status; verified in code 2026-09-01.**

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
**Found by measuring whether the two stores agree. They did not.**

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
that SQLite has lost. Under the new model every routine question becomes a ticket, so the volume of rows
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

## 8. Decisions taken

1. **The customer sees a reference only when the ticket is serviceable.** A logging id is internal.
2. **Logging tickets are never synced to Jira** — a filter at the sync boundary. The record stays in
   our store so a future logging/monitoring system can read it.
3. **The referee was measured before anything was built** — 10/10 on hand-labelled cases was the gate the design had to pass.
