# Demo Script

One run per customer. **Type each question exactly as written** — wordings were chosen so the LLM
and the rule classifier agree; rewording can misroute mid-demo.

Each run is a story, not a checklist. **Three threads run at the same time** — a distress thread
(card / account / loan), a claims thread and a payments thread — and the customer jumps between them
the way a real person does, while the system keeps four tickets straight.

**Expect** = the value the reply must contain. **Panel** = open *"Why this answer"* there.

---

# Run 1 — Sayantini Sarkar · 16 steps · ~9 min
HNI · Mastercard **45 days past due** · FD · Health policy · 3 claims in 3 states
*Richest graph, Attrition risk **High**. Four tickets across three threads. The default run.*

**Threads:** 💳 card distress · 🏥 claims · 💰 payments

| # | Say this | | Expect | Watch |
|---|---|---|---|---|
| 1 | What is my credit card limit? | 💳 | `Rs.1,065,000` | panel: **graph** · CreditCard |
| 2 | When is my credit card payment due? | 💳 | `2026-07-08` — past due | |
| 3 | I want to dispute a charge on my credit card | 💳 | ticket **A** `:card` | |
| 4 | The disputed charge is the Rs.1,258 late payment fee on my Mastercard | 💳 | **ticket A** | scope refined |
| 5 | What is the status of my claim CLM001003? | 🏥 | Under Review · awaiting documents | |
| 6 | Why was my claim CLM001001 rejected? | 🏥 | filed after coverage lapse | comparing outcomes |
| 7 | What documents do you need for claim CLM001003? | 🏥 | ticket **B** | |
| 8 | I want to dispute the Rs.29,419 NEFT debit to Neelofar Kumar | 💰 | ticket **C** `:neft` | **three** open |
| 9 | Any update on my disputed card charge? | 💳 | → **ticket A** | |
| 10 | Any update on the documents for my claim? | 🏥 | → **ticket B** | |
| 11 | How do I file a health insurance claim? | — | `24-48 hours` | panel: **KB** ← the contrast |
| 12 | Any update on my disputed transaction? | 💰 | → **ticket C** | |
| 13 | When is my next insurance premium due? | 🏥 | `2026-10-23` | |
| 14 | I also want to dispute a UPI payment to Kartik Kulkarni | 💰 | ticket **D** `:upi` | **four** open |
| 15 | Do I have anything pending with you? | — | names the open tickets | no reference given |
| 16 | Any update on my disputed card charge? | 💳 | → **ticket A** still | correct at the end |

**Steps 9-12 are the hard part** — four consecutive follow-ups, each to a *different* thread, each
picking the right ticket from three open.

**Grounding:** `TXN0001000012` Rs.29,419.08 NEFT Neelofar Kumar — *Pending, "Processing at
beneficiary bank"*. `TXN0001000014` Rs.5,220.47 UPI Kartik Kulkarni — *Debited-Pending-Credit*.
Card `CC00100001` — *"Late payment fee Rs.1258 applied"*, DPD 45. Claims `CLM001001` Rejected ·
`CLM001002` Approved · `CLM001003` Under Review.

---

# Run 2 — Digvijay Yadav · 14 steps · ~8 min
Affluent · 2 savings accounts (one **below minimum**) · matured FD · Home policy · 3 claims in 3 states
*Service-recovery story. Four tickets across three threads.*

**Threads:** 🏦 account/charge · 🏠 claims · 💰 payments

| # | Say this | | Expect | Watch |
|---|---|---|---|---|
| 1 | What is my account balance? | 🏦 | `14,624` (+ second account) | panel: **graph** · Account |
| 2 | My savings account is below the minimum balance, what are my options? | 🏦 | `Rs.2,507` vs `Rs.3,000` min | |
| 3 | I want to dispute the non-maintenance charge on my account | 🏦 | ticket **A** `:other` | |
| 4 | What is the status of my claim CLM001010? | 🏠 | Processing · assessor scheduled | |
| 5 | Why was my claim CLM001009 rejected? | 🏠 | filed after coverage lapse | comparing outcomes |
| 6 | What documents do you need for claim CLM001010? | 🏠 | ticket **B** | |
| 7 | I want to dispute a charge on my account | 💰 | ticket **C** `:other` | **three** open |
| 8 | The disputed charge is the Rs.41,223 UPI debit to Romil Halder | 💰 | **ticket C** | scope → `:upi` |
| 9 | What is a Demat account? | — | electronic holding of securities | panel: **KB** ← the contrast |
| 10 | Any update on my disputed account charge? | 🏦 | → **ticket A** | |
| 11 | Any update on the documents for my claim? | 🏠 | → **ticket B** | |
| 12 | Any update on my disputed UPI payment? | 💰 | → **ticket C** | |
| 13 | I also want to dispute the Rs.13,055 ATM withdrawal that failed | 💰 | ticket **D** `:atm` | **four** open |
| 14 | Do I have anything pending with you? | — | names the open tickets | |

**Steps 10-12 are the hard part** — three consecutive follow-ups, three different threads.

**Step 2 bridge:** account `40900000100004` holds `Rs.2,507` against a `Rs.3,000` minimum with a
`Rs.658.56` non-maintenance charge — a natural lead into the attrition panel and offers card.

**Grounding:** `TXN0001000045` Rs.41,223.59 UPI Romil Halder — *Debited-Pending-Credit*.
`TXN0001000044` Rs.13,055.06 ATM — *Failed, "Beneficiary bank server timeout"*. Claims `CLM001008`
Approved · `CLM001009` Rejected · `CLM001010` Processing.

---

# Run 3 — Fathima Devasahayam · 14 steps · ~8 min
Affluent · Personal loan (**EMI overdue**) · Term + Auto policies · 3 claims in 3 states
*Collections/hardship story. Four tickets across three threads. The customer continuity was proven live on.*

**Threads:** 🏦 loan distress · 🚗 claims · 💰 payments

| # | Say this | | Expect | Watch |
|---|---|---|---|---|
| 1 | What is my loan status? | 🏦 | `LN001002` · EMI overdue | panel: **graph** · Loan |
| 2 | What is my EMI due date? | 🏦 | next payment date | |
| 3 | I want to dispute the penalty charged on my loan | 🏦 | ticket **A** `:other` | |
| 4 | What is the status of my claim CLM001014? | 🚗 | Under Review · awaiting documents | |
| 5 | What documents do you need for claim CLM001014? | 🚗 | ticket **B** | |
| 6 | I want to dispute a transaction on my account | 💰 | ticket **C** `:other` | **three** open |
| 7 | The disputed charge is the Rs.28,991 IMPS payment to Kimaya Seth | 💰 | **ticket C** | scope → `:imps` |
| 8 | What is the maximum daily ATM withdrawal limit? | — | `Rs.10,000`-`Rs.50,000` | panel: **KB** ← the contrast |
| 9 | Any update on my disputed penalty? | 🏦 | → **ticket A** | |
| 10 | Any update on the documents for my claim? | 🚗 | → **ticket B** | |
| 11 | Any update on my disputed IMPS payment? | 💰 | → **ticket C** | |
| 12 | When is my term insurance premium due? | 🚗 | `2026-07-02` | |
| 13 | I also want to dispute the Rs.5,188 NEFT debit to Hansh Bir | 💰 | ticket **D** `:neft` | **four** open |
| 14 | Do I have anything pending with you? | — | names the open tickets | |

**Steps 9-11 are the hard part** — three consecutive follow-ups, three different threads.

**Grounding:** `TXN0001000067` Rs.28,991.63 IMPS Kimaya Seth — *Pending, "Awaiting bank
confirmation"*. `TXN0001000058` Rs.5,188.46 NEFT Hansh Bir — *Failed, "Invalid beneficiary
details"*. Claims `CLM001013` Processing · `CLM001014` Under Review · `CLM001015` Approved.

---

# What each run proves

**Three threads, not one.** Each run carries a distress thread (card / account / loan), a claims
thread, and a payments thread — running at the same time, interleaved the way a real customer talks.
A scripted demo asks its questions in tidy blocks and never shows this.

**Refinement** — a vague dispute becomes specific without forking (`:other` → `:card`/`:upi`/`:imps`).

**Matching back across threads** — every *"Any update on…"* step classifies as `ticket_status` or
`claim_status`, a **different intent** from the ticket it belongs to, and still lands on the right
one. The consecutive-follow-up blocks are the proof: three or four in a row, each to a different
thread, each with three or four tickets open to choose from.

**Comparing outcomes** — *"Why was CLM001001 rejected?"* when another claim was approved is a real
customer question, not an ID read off a script. Each customer has three claims in three states.

**Forking** — the *"I also want to dispute…"* step has the same intent as an existing dispute and
the word "also", and still opens a separate ticket.

**Memory** — *"Do I have anything pending?"* names the open cases with no reference given.

**Where to point:** in **Lineage**, each thread is ONE row with its exchanges as dots — not one row
per message. In **Detailed**, ticket A is ONE request containing its steps even though two other
threads happened in between.

---

# Before you present — read once

**Dispute and follow-up steps hold for review.** The customer gets *"Support Agent will help you
shortly…"* and the real answer waits under **Needs Review**. Approve on screen as part of the story
(it is a good human-in-the-loop moment) or skip those steps. Roughly half of each run holds.
→ *Fast, no interruptions: the first 5 steps of any run.*

**Continuity is an LLM judgement call**, not bit-for-bit repeatable. Bias: merge when unsure on a
vague ticket, fork when unsure elsewhere — a visible fork is fixable, a silent merge hides a
complaint. **Rehearse each run once.**

**The consecutive follow-up blocks are the riskiest part of the demo.** Each run reaches **four open
tickets**, and the *"Any update on…"* steps ask the referee to pick the right one. Wordings differ
deliberately — "card charge" vs "transaction", "the documents for my claim" vs "disputed penalty" —
to give it something to match on. Two open tickets of the same intent is the documented ambiguity
limit, and these runs deliberately go past it: **rehearse these blocks, and know which step you
would skip if one mis-matches live.**

**The claims thread is less proven than the disputes thread.** Continuity was built and tested on
transaction disputes; the claim follow-ups (*"Any update on the documents for my claim?"*) classify
`claim_status`/`insurance_claim` and rely on the referee gathering candidates by conversation across
any intent. That path is real (it is what makes the dispute follow-ups work) but has not been
exercised on claims end-to-end.

**"Any update…" holds for review** even when it attaches correctly — an L2 classification escalates
before the "ticket_status never creates a ticket" rule is reached.

**Provenance shows only on fresh replies.** Retrieval evidence is written once when a reply is sent,
so turns created before 2026-08-19 keep the old label. Do not scroll back to old history to
demo the panel.

---

# Verification status

**Intent + ticket scope verified 2026-08-21** for every step in all three runs (`classify_intent` +
`_ticket_scope`), 0 Groq, 0 turns created. Record values read from `data/bfsi.xlsx`, the seed the
graph is built from.

**Not yet run end-to-end.** These interleaved runs are longer and hold more tickets open at once than
anything that has been executed live — expectations come from the matching rules, not observation.

**Live end-to-end:** the continuity pattern was run on **Fathima** and passed — one ticket across
three messages, a separate ticket for the separate matter, including a follow-up matching across an
intent boundary. The longer interleaved runs above have **not** been run end-to-end.

**The model changed 2026-08-19.** Groq removed every Llama model (they now 404); the app runs on
`openai/gpt-oss-20b`. Intent and scope were re-verified, but the live run above was measured on the
old model. Non-determinism is more visible now: *"Any update on my dispute?"* was observed
classifying as `ticket_status` on one run and `transaction_dispute` on another **within the same
hour**. Both reach the right ticket; the panel may show either the ticket-record state or the graph
state. Do not promise one in advance.

**Discarded wordings** (verified wrong, do not use): *"It was the Rs.5,776 IMPS **transfer**"* and
*"the Rs.5,188 NEFT **transfer**"* → `fund_transfer`; *"I also **have a problem with** a UPI
payment"* → `general_inquiry`; *"Why is there a late payment fee"* → `card_management`; *"my card is
**45 days overdue**"* → `loan_default_notice`; *"Can you **waive** the fee"* → `general_inquiry`
(0.45); *"**Why was** a non-maintenance charge applied"* and *"**Why is there** a penalty on my
loan"* → `general_inquiry` (use *"I want to dispute the…"* instead); *"My EMI is overdue, what are
my repayment options"* → `loan_default_notice`.

---

# Spares

| Customer | Question | Expect |
|---|---|---|
| Sayantini | The disputed charge is the Rs.5,776 IMPS payment to Samarth Thaker | `TXN0001000003`, Debited-Pending-Credit |
| Digvijay | The disputed charge is the Rs.46,092 ATM withdrawal on 25 May | `TXN0001000043`, Success (no failure reason) |
| Sireesha | What is my credit card limit? | `Rs.75,000` |
| Sireesha | What is the status of my home insurance claim? | `CLM001005` |
| Sireesha | When is my next premium due? | `2026-11-28` |
| Hirithi | What is my loan status? | `LN001001` |
| Hirithi | What is my credit card limit? | `Rs.830,000` |
| Hirithi | What is the status of my theft claim? | `CLM001011` |
| Hirithi | When is my car insurance premium due? | `2027-04-15` |
| Digvijay | What is the status of my claim CLM001008? | Approved · documents verified |
| Fathima | What is the status of my theft claim? | `CLM001013` · Processing |

**Hirithi holds every product type** — useful if you want one customer exercising every graph path.
Her 4 questions ran live and all returned `neo4j_graph`.

Other indexed FAQs: opening a savings account, personal loan requirements, lost/stolen card, home
loan, SIP, ELSS, term insurance, car insurance premium factors, ULIP, KYC update, policy porting.

---

# Known gaps

- **Unverified senders** get "Dear Customer" and no graph data — by design.
- **In the graph but never read when answering:** `ChargePenalty` (7), `KYC` (5), `Product` (20,
  offers only), `Interaction` (21, seeded). A penalty or KYC question answers from the KB.
- **Seed dates are ageing.** Sayantini's card due date has passed; 3 of 4 FDs are `Matured`. Answers
  are correct about the record — they just describe the past.
- **Multi-account customers** (Sireesha, Digvijay, Fathima) get *both* accounts in a balance answer,
  with no way to disambiguate a follow-up.
- **No continuity for unticketed topics.** The unrelated questions in each run are not linked to each
  other — replies stay coherent (last 8 turns) but nothing groups them in the record. Designed,
  deferred.
- The **Escalate** button is a UI stub — do not click it during a demo.
