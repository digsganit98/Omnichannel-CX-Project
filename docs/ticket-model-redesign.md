# Ticket model redesign — analysis and plan

**Proposal (user's):** every customer query gets a ticket id. The existing rules keep deciding
the *hold*. A ticket starts as a **logging id**, and becomes **serviceable** the moment something
in that thread needs a human. Grouping is by *matter*, not by intent label; a genuine topic change
gets a new id and the reply says so.

Everything below was measured against the live system on 2026-09-01. No code has been changed.

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

**The customer gets a reference for everything.** *"Logged under TKT-123"* on a routine question is
normal bank behaviour and gives them something to quote on any channel.

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

---

## 6. Plan

### Phase 0 — Measure the referee (no code)
Replay real message pairs through `_referee_match` and score its answers against a hand-labelled
expectation. Include: a status follow-up, a second dispute about a different charge, a topic change,
and a cross-channel follow-up.

**Gate: if the referee cannot reliably tell same-matter from new-matter, stop.** The whole design
rests on it. Cost: ~15 calls, ~10K tokens.

### Phase 1 — Separate the two decisions (no behaviour change)
Introduce `ticket_required` (always true) and `hold_required` (today's rules) as distinct values,
with `hold_required` wired to the review gate exactly as `required` is now. **Ship with
`ticket_required` still gated**, so nothing changes yet. This is the refactor that makes the rest
safe.

### Phase 2 — Add the `logged` status
Enum value + migration + every read site. Follow Fix 109's method: make every site accept exactly
one word, so a wrong value is visible immediately rather than silently tolerated.

### Phase 3 — Guard the surfaces (before opening the tap)
`get_open_cases` excludes `logged`. Right-panel card shows serviceable only. Jira sync skips
`logged`. Analytics denominators reviewed. **This must land before Phase 4**, or the first
logging ticket corrupts the reply prompt.

### Phase 4 — Create a ticket for every query
Remove the `required` gate from creation. Referee runs on every message. Promote to `open` on the
first hold.

### Phase 5 — Topic-change acknowledgement
When the referee answers NEW and an open thread exists, the reply notes it is a separate matter.

---

## 7. Recommendation

**The design is right.** It fixes the UI grouping at its root rather than with a proxy, and it
separates two decisions that were never the same question.

**Do Phase 0 first, and let it decide.** Everything rests on the referee, and its behaviour at this
volume is unmeasured. One measurement is cheap; discovering it silently merges unrelated matters
after Phase 4 is not.

**Phases 1-3 are the real work** — the meaning change across analytics, the prompt, the panel and
Jira is larger than the ticket-creation change itself. Phase 4 is a few lines once they are done.

**Consider 5.6 alongside this.** Moving `case_summary` and `opportunity_generation` off the message
path frees ~35% of per-message tokens — more than this design costs — and is independent of it.

---

## 8. Decisions taken

1. **The customer sees a reference only when the ticket is serviceable.** A logging id is internal.
2. **Logging tickets are never synced to Jira** — a filter at the sync boundary. The record stays in
   our store so a future logging/monitoring system can read it.
3. **Phase 0 is the gate.** Measure the referee before anything else is built.
