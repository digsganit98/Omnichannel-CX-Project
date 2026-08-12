# Demo Script — grounded, sequenced, per customer

Three self-contained demo runs. Each is an **ordered sequence**, not a list to pick from: it opens
with instant graph-backed answers, adds a knowledge-base answer, then builds a multi-message dispute
that shows ticket continuity — and ends by proving the system also *refuses* to merge two genuinely
different matters.

**Expect** is the exact value the reply must contain. If it is missing, something is wrong — do not
assume it is a wording difference.

**Verified 2026-08-12**, after Fixes 66-72, against the post-fresh-start seed:
- **All 29 questions below** checked offline (`classify_intent` + `_ticket_scope` + `neo4j_answer`) —
  correct intent, correct ticket scope, and the expected value present in the customer's records.
  0 Groq, 0 turns created.
- **The continuity pattern** (steps 7-10) was additionally run **live end-to-end on Fathima** and
  passed: one ticket across three messages, a separate ticket for the separate matter.

> **Phrasing is deliberate.** Earlier drafts used "It was the Rs.5,776 IMPS **transfer**…", which the
> rule classifier reads as `fund_transfer`, and "I also **have a problem with** a UPI payment", which
> it reads as `general_inquiry`. Both were corrected to wordings the LLM *and* the rule classifier
> agree on, so a fallback can never land on the wrong intent mid-demo. **Use these wordings as
> written.**

---

## What each step is meant to show

| Steps | Shows | Panel should read |
|---|---|---|
| 1-4 | Instant answers from the customer's own records | `retrieval · neo4j_graph` |
| 5 | An answer from the knowledge base | `retrieval · opensearch_vector` / `keyword_fallback` |
| 6 | A held reply — human-in-the-loop review | draft under **Needs Review** |
| 7-9 | **Ticket continuity** — one matter, three messages, one ticket | one ticket id throughout |
| 10 | **Correct separation** — a different matter forks | a *second* ticket id |

---

# Run 1 — Sayantini Sarkar (CRN00010001)
**HNI · Hyderabad · 61 months · sayantini.s.55@gmail.com · 917890864700**
CSA salary account · Mastercard Classic (**45 days past due**) · FD · Health policy · 3 claims

The strongest single customer: the richest knowledge graph, a distressed card driving
**Attrition risk: High**, and three claims in three different states.

| # | Say this | Expect | Intent |
|---|---|---|---|
| 1 | What is my credit card limit? | `Rs.1,065,000` | card_management |
| 2 | When is my credit card payment due? | `2026-07-08` | card_management |
| 3 | When is my FD maturity date? | `2028-01-12` | account_balance_inquiry |
| 4 | When is my next insurance premium due? | `2026-10-23` | policy_status |
| 5 | How do I file a health insurance claim? | cashless: inform insurer/TPA within `24-48 hours` | insurance_claim |
| 6 | What is the status of my insurance claim? | `CLM001003` · Under Review | claim_status |
| 7 | I want to dispute a transaction on my account | ticket opens, scope `:other` | transaction_dispute |
| 8 | The disputed charge is the Rs.5,776 IMPS payment to Samarth Thaker | **same ticket**, scope → `:imps` | transaction_dispute |
| 9 | Any update on my dispute? | **same ticket** | ticket_status |
| 10 | I also want to dispute a UPI payment to Kartik Kulkarni | **NEW ticket** | transaction_dispute |

**Why steps 8 and 10 are real.** `TXN0001000003` (Rs.5,776.55, IMPS, Samarth Thaker) and
`TXN0001000014` (Rs.5,220.47, UPI, Kartik Kulkarni) are both genuinely
**`Debited-Pending-Credit`** in her records, with the reason *"Beneficiary bank delayed crediting —
auto-reversal in progress."* Two real stuck payments, so the dispute and the second dispute are both
legitimate.

**Point at:** after step 9, one request node in **Detailed** containing three exchanges. After step
10, **two** rows in **Lineage** — because there are two problems.

---

# Run 2 — Digvijay Yadav (CRN00010003)
**Affluent · 16 months · digvijayyadav48@gmail.com**
2 savings accounts (one **below minimum balance**) · matured FD · Home policy · 3 claims

Best for the *service-recovery* story: an account under its minimum with a penalty charge already
applied, and three home-insurance claims that resolved three different ways.

| # | Say this | Expect | Intent |
|---|---|---|---|
| 1 | What is my account balance? | `14,624` (and the second account) | account_balance_inquiry |
| 2 | What is my fixed deposit maturity amount? | `1,094,768` | account_balance_inquiry |
| 3 | When is my home insurance premium due? | `2026-09-01` | policy_status |
| 4 | What is the status of my claim? | `CLM001010` · Processing | claim_status |
| 5 | What is a Demat account? | electronic holding of securities | general_inquiry |
| 6 | I want to dispute a transaction | ticket opens, scope `:other` | transaction_dispute |
| 7 | The disputed charge is the Rs.46,092 ATM withdrawal on 25 May | **same ticket**, scope → `:atm` | transaction_dispute |
| 8 | Any update on my dispute? | **same ticket** | ticket_status |
| 9 | I also want to dispute a UPI payment to Tiya Varma | **NEW ticket** | transaction_dispute |

**Talking point on step 1:** account `40900000100004` holds `Rs.2,507` against a `Rs.3,000` minimum
and already carries a `MinBalanceNonMaintenance` charge of `Rs.658.56`. A natural bridge into the
attrition-risk panel and the offers card.

**Honest note:** unlike Sayantini and Fathima, **all of Digvijay's transactions are `Success`** — the
ATM withdrawal and the UPI payment are real records, but neither is a *failed* payment. The dispute
is plausible (a customer can dispute a successful debit) but the reply will not mention a failure
reason. Use Run 1 or Run 3 if you want the stuck-payment story.

---

# Run 3 — Fathima Devasahayam (CRN00010005)
**Affluent · 20 months · fathimawork511@gmail.com**
2 savings accounts · Personal loan (**EMI overdue**) · Term + Auto policies · 3 claims

The collections/hardship story: an overdue EMI, a disputed penalty charge already on file, and the
customer this continuity flow was **proven live on**.

| # | Say this | Expect | Intent |
|---|---|---|---|
| 1 | What is my loan status? | `LN001002` · EMI overdue | loan_status |
| 2 | What is my savings account balance? | `5,446` (and the second account) | account_balance_inquiry |
| 3 | When is my term insurance premium due? | `2026-07-02` | policy_status |
| 4 | What is the status of my theft claim? | `CLM001013` · Processing | claim_status |
| 5 | What is the maximum daily ATM withdrawal limit? | `Rs.10,000`-`Rs.50,000` for savings | general_inquiry |
| 6 | I want to dispute a transaction on my account | ticket opens, scope `:other` | transaction_dispute |
| 7 | The disputed charge is the Rs.28,991 IMPS payment to Kimaya Seth | **same ticket**, scope → `:imps` | transaction_dispute |
| 8 | Any update on my dispute? | **same ticket** | ticket_status |
| 9 | I also want to dispute a UPI payment to Jivin Vora | **NEW ticket** | transaction_dispute |

**Why step 7 is real.** `TXN0001000067` (Rs.28,991.63, IMPS, Kimaya Seth) is genuinely **`Pending`**
with the reason *"Awaiting bank confirmation."*

**This exact sequence was run live and passed** — including step 8 matching back to the dispute
ticket despite classifying as a *different intent*, which is what Fix 72 repaired.

---

## Two rough edges to know before you present

**1. Step "Any update on my dispute?" is still held for review.** It attaches to the correct ticket,
but the customer sees *"Support Agent will help you shortly…"* rather than the status. The cause is
in the escalation rules, not continuity: an L2 classification escalates before the
"ticket_status never creates a ticket" rule is reached. **Either approve the draft on screen** (it is
a good human-in-the-loop moment) **or skip that step.**

**2. The continuity decisions are LLM judgement calls**, so they are not bit-for-bit repeatable. The
bias is set to merge when unsure on a vague ticket, and to fork when unsure elsewhere — a visible
fork is fixable, a silent merge hides a complaint. **Rehearse each run once** rather than assuming a
given run repeats.

---

## Which questions hold for review

Dispute, loan and claim questions usually classify L2/L3 and are **held** — the customer gets the
holding message and the real answer waits as a draft under **Needs Review**. Card, balance, premium
and FAQ questions usually **auto-send**.

- **Want a fast, no-interruption demo?** Steps 1-5 of any run.
- **Want to show human-in-the-loop?** Continue to the dispute steps and approve drafts on screen.

---

## Other verified questions (spares)

Grounded and checked, if you need to go off-script:

| Customer | Question | Expect |
|---|---|---|
| Sayantini | What is my account balance? | `40900000100001` |
| Sireesha (CRN00010002) | What is my credit card limit? | `Rs.75,000` |
| Sireesha | What is the status of my home insurance claim? | `CLM001005` |
| Sireesha | When is my next premium due? | `2026-11-28` |
| Hirithi (CRN00010004) | What is my loan status? | `LN001001` |
| Hirithi | What is my credit card limit? | `Rs.830,000` |
| Hirithi | What is the status of my theft claim? | `CLM001011` |
| Hirithi | When is my car insurance premium due? | `2027-04-15` |

**Hirithi is the only customer holding every product type** (current account, card, FD, loan, policy,
claims) — useful if you want one customer who exercises every graph path. Her 4 questions were run
live and all returned `retrieval_backend: neo4j_graph`.

Remaining indexed FAQs: opening a savings account, personal loan requirements, reporting a lost or
stolen card, applying for a home loan, SIP, ELSS tax benefits, term insurance, car insurance premium
factors, ULIP vs traditional plans, KYC update, policy porting.

---

## Known gaps

- **Unverified senders** get "Dear Customer" and no graph data — by design (Fix 59/60).
- **In the graph but never read when answering:** `ChargePenalty` (7 nodes), `KYC` (5), `Product`
  (20, offers engine only), `Interaction` (21, seeded history). A question about a penalty charge or
  KYC status answers from the KB, not the customer's record.
- **Seed dates are fixed and ageing.** Sayantini's card due date (`2026-07-08`) is already past, and
  3 of 4 FDs are `Matured` with 2021-2023 dates. Answers are correct about the record; they simply
  describe the past.
- **Multi-account customers** (Sireesha, Digvijay, Fathima) get *both* accounts in a balance answer,
  with no way to disambiguate "my savings account" in a follow-up.
- **No continuity for unticketed topics.** Two card questions with no ticket are not linked as one
  matter — the LLM still sees the last 8 turns, so *replies* stay coherent, but nothing groups them
  in the record. Persistent threading is designed and deferred.
- The **Escalate** button is a UI stub — do not click it during a demo.
