# Demo Script

Three ordered runs. **Type the question exactly as written** — wordings were chosen so the LLM and
the rule classifier agree; a reworded question can misroute mid-demo.

**Expect** = the value the reply must contain. **Panel** = open *"Why this answer"* on that step.

| Pick one | Steps | Time | When |
|---|---|---|---|
| **Run 1** | 11 | ~5 min | Feature-by-feature. Tidy blocks, easy to narrate. |
| **Run 1 Extended** | 15 | ~8 min | The story. She interleaves topics; 3 tickets stay straight. |
| Run 2 / Run 3 | 9 | ~4 min | Different customer stories (service recovery, hardship). |

---

# Run 1 — Sayantini Sarkar
HNI · Hyderabad · Mastercard **45 days past due** · FD · Health policy · 3 claims
*Richest graph, Attrition risk **High**. The default run.*

| # | Say this | Expect | Panel |
|---|---|---|---|
| 1 | What is my credit card limit? | `Rs.1,065,000` | **graph** · CreditCard |
| 2 | When is my credit card payment due? | `2026-07-08` | |
| 3 | When is my FD maturity date? | `2028-01-12` | **graph** · Account + FD |
| 4 | When is my next insurance premium due? | `2026-10-23` | |
| 5 | How do I file a health insurance claim? | inform insurer/TPA within `24-48 hours` | **KB** ← the contrast |
| 6 | What is the status of my insurance claim? | `CLM001003` · Under Review | |
| 7 | I want to dispute a transaction on my account | ticket opens, scope `:other` | |
| 8 | The disputed charge is the Rs.5,776 IMPS payment to Samarth Thaker | **same ticket** → `:imps` | |
| 9 | Any update on my dispute? | **same ticket** | **case banner** · 3 messages |
| 10 | I also want to dispute a UPI payment to Kartik Kulkarni | **NEW ticket** | |
| 11 | Do I have anything pending with you? *(optional close)* | names **both** tickets | |

**Step 5 is the one that matters.** A panel saying "graph" on every reply proves nothing. Same
customer, same chat, KB answer — and the panel says so.

**Step 9** classifies as a *different intent* (`ticket_status`) and still lands on the right ticket.

---

# Run 1 Extended — Sayantini, the mixed story (15 steps)

Use **instead of** Run 1 when you want the full story rather than a feature checklist. Same
customer, ~8 minutes. She interleaves topics the way a real person does — the point is that the
system keeps three separate matters straight while she jumps between them.

**The story:** her card is 45 days overdue with a late fee. While sorting that out she notices a
stuck transfer. Then she asks about unrelated things. Then she comes back to both.

| # | Say this | Expect | Watch |
|---|---|---|---|
| 1 | What is my credit card limit? | `Rs.1,065,000` | panel: **graph** · CreditCard |
| 2 | When is my credit card payment due? | `2026-07-08` (past due) | |
| 3 | I want to dispute a charge on my credit card | ticket **A** opens, `:card` | |
| 4 | The disputed charge is the Rs.1,258 late payment fee on my Mastercard | **ticket A** stays | scope refined |
| 5 | When is my FD maturity date? | `2028-01-12` | **topic switch** — no new ticket |
| 6 | I want to dispute the Rs.29,419 NEFT debit to Neelofar Kumar | ticket **B** opens, `:neft` | **two** open tickets |
| 7 | How do I file a health insurance claim? | `24-48 hours` | panel: **KB** ← the contrast |
| 8 | Any update on my disputed card charge? | **ticket A** | matched back after 4 unrelated steps |
| 9 | Any update on my disputed transaction? | **ticket B** | correct one of two |
| 10 | When is my next insurance premium due? | `2026-10-23` | |
| 11 | What is the status of my insurance claim? | `CLM001003` · Under Review | |
| 12 | I also want to dispute a UPI payment to Kartik Kulkarni | ticket **C**, `:upi` | **three** open |
| 13 | Do I have anything pending with you? | names the open tickets | no reference given |
| 14 | What is my account balance? | `40900000100001` | |
| 15 | Any update on my disputed transaction? | **ticket B** again | still correct at the end |

## What each part proves

**Steps 3-4 — refinement.** A vague dispute becomes specific without forking. Ticket A goes
`:other` → `:card`.

**Steps 5, 7, 10-11, 14 — the interleaving.** Five unrelated questions scattered through the run.
None creates a ticket; none disturbs A, B or C. This is the part a scripted demo never shows,
because a scripted demo asks its questions in tidy blocks.

**Steps 8-9 — the hard bit.** Two open disputes, two follow-ups, each has to land on the right one.
Both classify as `ticket_status` — a *different intent* from the disputes they belong to — and step
8 matches back across **four intervening messages**.

**Step 12 — it still forks.** Same intent as A and B, the word "also", and it opens a third ticket
rather than merging into either.

**Step 13 — memory.** No amount, no reference, no product named.

**Step 15 — it holds.** The same follow-up as step 9, fifteen messages in, three open tickets. Still
resolves to B.

## Where to point

**Lineage:** three rows, not fifteen. Each dispute is one row with its exchanges as dots; the
unrelated questions sit in their own theme groups.

**Detailed:** ticket A appears as ONE request containing steps 3, 4 and 8 — even though step 5 and
6 happened in between. That is the interleaving fix; without it A would render as two rows under
two headers.

## Honest notes

- **Steps 3, 4, 6, 8, 9, 12, 13, 15 hold for review.** That is 8 drafts. Approve them on screen as
  part of the story, or run the short Run 1 instead if you want fewer interruptions.
- **Two open tickets of the same intent is the known ambiguity limit.** Steps 8/9 ask the referee to
  pick between A and B. It is given both as candidates and the wordings differ ("card charge" vs
  "transaction"), but this is the hardest thing in the demo and the one most likely to vary.
  **Rehearse it.**
- **Step 15 is optional** — it is a repeat of step 9 purely to show durability. Drop it if time is
  short.
- Intent and ticket scope for all 15 steps verified **2026-08-21** offline (0 Groq, 0 turns).
  Not yet run end-to-end.

---

# Run 2 — Digvijay Yadav
Affluent · 2 savings accounts (one **below minimum**) · matured FD · Home policy · 3 claims
*Service-recovery story.*

| # | Say this | Expect | Panel |
|---|---|---|---|
| 1 | What is my account balance? | `14,624` (+ second account) | **graph** · Account |
| 2 | What is my fixed deposit maturity amount? | `1,094,768` | |
| 3 | When is my home insurance premium due? | `2026-09-01` | |
| 4 | What is the status of my claim? | `CLM001010` · Processing | |
| 5 | What is a Demat account? | electronic holding of securities | **KB** ← the contrast |
| 6 | I want to dispute a transaction | ticket opens, scope `:other` | |
| 7 | The disputed charge is the Rs.46,092 ATM withdrawal on 25 May | **same ticket** → `:atm` | |
| 8 | Any update on my dispute? | **same ticket** | **case banner** |
| 9 | I also want to dispute a UPI payment to Tiya Varma | **NEW ticket** | |

**Step 1 bridge:** account `40900000100004` holds `Rs.2,507` against a `Rs.3,000` minimum, with a
`Rs.658.56` non-maintenance charge — a natural lead into the attrition panel and offers card.

**Note:** all of Digvijay's transactions are `Success`, so his dispute reply names no failure reason.
Use Run 1 or 3 for the stuck-payment story.

---

# Run 3 — Fathima Devasahayam
Affluent · Personal loan (**EMI overdue**) · Term + Auto policies · 3 claims
*Collections/hardship story. This is the run proven live end-to-end.*

| # | Say this | Expect | Panel |
|---|---|---|---|
| 1 | What is my loan status? | `LN001002` · EMI overdue | **graph** · Loan |
| 2 | What is my savings account balance? | `5,446` (+ second account) | |
| 3 | When is my term insurance premium due? | `2026-07-02` | |
| 4 | What is the status of my theft claim? | `CLM001013` · Processing | |
| 5 | What is the maximum daily ATM withdrawal limit? | `Rs.10,000`-`Rs.50,000` | **KB** ← the contrast |
| 6 | I want to dispute a transaction on my account | ticket opens, scope `:other` | |
| 7 | The disputed charge is the Rs.28,991 IMPS payment to Kimaya Seth | **same ticket** → `:imps` | |
| 8 | Any update on my dispute? | **same ticket** | **case banner** |
| 9 | I also want to dispute a UPI payment to Jivin Vora | **NEW ticket** | |

---

# Before you present — read once

**Dispute/loan/claim steps hold for review.** The customer gets *"Support Agent will help you
shortly…"* and the real answer waits under **Needs Review**. Either approve the draft on screen (a
good human-in-the-loop moment) or skip. Card/balance/premium/FAQ steps auto-send.
→ *Fast demo with no interruptions: steps 1-5 of any run.*

**Continuity is an LLM judgement call**, not bit-for-bit repeatable. Bias: merge when unsure on a
vague ticket, fork when unsure elsewhere. **Rehearse each run once.**

**"Any update on my dispute?" holds for review** even though it attaches correctly — an L2
classification escalates before the "ticket_status never creates a ticket" rule is reached.

**Provenance shows only on fresh replies.** Evidence is written once when a reply is sent, so turns
created before 2026-08-19 keep the old label. Don't scroll back to old history to demo the panel.

---

# Verification status

**Intent + ticket scope: all 29 questions re-checked 2026-08-19** (`classify_intent` +
`_ticket_scope`), 0 Groq, 0 turns created. Values read from the live Neo4j records.

**Live end-to-end:** the continuity pattern was run on **Fathima** and passed — one ticket across
three messages, a separate ticket for the separate matter, including step 8 matching across an
intent boundary.

**Caveat — the model changed 2026-08-19.** Groq removed every Llama model (they now 404); the app
runs on `openai/gpt-oss-20b`. Intent and scope were re-verified, but the *live* run above was
measured on the old model. Non-determinism is more visible now: *"Any update on my dispute?"* was
observed classifying as `ticket_status` on one run and `transaction_dispute` on another **within the
same hour**. Both reach the right ticket; the panel may show either the ticket-record state or the
graph state. Don't promise one in advance.

**Grounding for the dispute steps.** Sayantini `TXN0001000003` (Rs.5,776.55 IMPS, Samarth Thaker) and
`TXN0001000014` (Rs.5,220.47 UPI, Kartik Kulkarni) are both **`Debited-Pending-Credit`** —
*"Beneficiary bank delayed crediting."* Fathima `TXN0001000067` (Rs.28,991.63 IMPS, Kimaya Seth) is
**`Pending`** — *"Awaiting bank confirmation."*

**Alternative pair for Sayantini steps 8/10**, if you prefer NEFT/UPI over IMPS/UPI (both verified):
`The disputed transaction is the Rs.29,419 NEFT debit to Neelofar Kumar` → `:neft`
(`TXN0001000012`, Pending), then `I also want to dispute the Rs.5,220 UPI debit to Kartik Kulkarni`
→ `:upi`.

---

# Spares

| Customer | Question | Expect |
|---|---|---|
| Sayantini | What is my account balance? | `40900000100001` |
| Sireesha | What is my credit card limit? | `Rs.75,000` |
| Sireesha | What is the status of my home insurance claim? | `CLM001005` |
| Sireesha | When is my next premium due? | `2026-11-28` |
| Hirithi | What is my loan status? | `LN001001` |
| Hirithi | What is my credit card limit? | `Rs.830,000` |
| Hirithi | What is the status of my theft claim? | `CLM001011` |
| Hirithi | When is my car insurance premium due? | `2027-04-15` |

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
- **Multi-account customers** get *both* accounts in a balance answer, with no way to disambiguate a
  follow-up.
- **No continuity for unticketed topics.** Replies stay coherent (last 8 turns) but nothing groups
  them in the record. Designed, deferred.
- The **Escalate** button is a UI stub — don't click it during a demo.
