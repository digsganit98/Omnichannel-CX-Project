# Demo Question Set — grounded in real seeded data

Every question below was **verified against the actual Neo4j records** before being listed:
the rule classifier routes it to an intent that unlocks a graph read, and `neo4j_answer`
returns that customer's record containing the **Expect** value.

Use the **Expect** column to check the answer on screen. If a reply does not contain that
value, something is wrong — do not assume it is a wording difference.

**Verified:** 2026-08-12, after Fixes 66-70, against the post-fresh-start seed.
**Verification method:** offline (`classify_intent` + `neo4j_answer`), 0 Groq, 0 turns created.
Regenerate with the scratchpad script `verify_questions.py` if the seed data ever changes.

---

## How the answer should be sourced

| Question type | Intent | Panel should show |
|---|---|---|
| FD / balance | `account_balance_inquiry` | `retrieval · neo4j_graph`, Account + FixedDeposit highlighted |
| Card | `card_management` | `retrieval · neo4j_graph`, CreditCard highlighted |
| Claim | `claim_status` | `retrieval · neo4j_graph`, Claim highlighted |
| Policy / premium | `policy_status` | `retrieval · neo4j_graph`, Policy highlighted |
| Loan | `loan_status` | `retrieval · neo4j_graph`, Loan highlighted |
| Transaction dispute | `transaction_dispute` | `retrieval · neo4j_graph`, Transaction highlighted |
| FAQ (below) | `general_inquiry` etc. | `retrieval · opensearch_vector` / `keyword_fallback` + the cited FAQ |

---

## Sayantini Sarkar — CRN00010001
**HNI · Hyderabad · 61 months · sayantini.s.55@gmail.com · 917890864700**
Holds: CSA salary account, Mastercard Classic, FD, Health policy, 3 claims.

| # | Question | Expect | Intent |
|---|---|---|---|
| 1 | When is my FD maturity date? | `2028-01-12` | account_balance_inquiry |
| 2 | What is my credit card limit? | `Rs.1,065,000` | card_management |
| 3 | When is my credit card payment due? | `2026-07-08` | card_management |
| 4 | What is my account balance? | `40900000100001` | account_balance_inquiry |
| 5 | What is the status of my insurance claim? | `CLM001003` | claim_status |
| 6 | When is my next insurance premium due? | `2026-10-23` | policy_status |
| 7 | I want to dispute a transaction on my account | `TXN0001000003` | transaction_dispute |

**Demo notes.** Richest customer — best for the knowledge-graph view. Her card is **45 days
past due** with `Rs.91,821.95` outstanding, which drives an **Attrition risk: High** band, and
her 3 claims are in three different states (Rejected / Approved / Under Review), so the graph
shows genuine variety. FD matures 2028-01-12 for `Rs.183,712` on a `Rs.160,000` principal.

---

## Sireesha — CRN00010002
**Mass Affluent · 49 months · s.sireesha28092004@gmail.com**
Holds: 2 savings accounts, Visa Signature, matured FD, Auto + Home policies, 4 claims.

| # | Question | Expect | Intent |
|---|---|---|---|
| 1 | What is my credit card limit? | `Rs.75,000` | card_management |
| 2 | What is the status of my home insurance claim? | `CLM001005` | claim_status |
| 3 | When is my next premium due? | `2026-11-28` | policy_status |
| 4 | What is my savings account balance? | `13,124` | account_balance_inquiry |

**Demo note.** Largest claim in the dataset — `Rs.12,72,618` structural damage, assessor visit
scheduled. Two savings accounts, so "balance" returns both.

---

## Digvijay Yadav — CRN00010003
**Affluent · 16 months · digvijayyadav48@gmail.com**
Holds: 2 savings accounts, matured FD, Home policy, 3 claims.

| # | Question | Expect | Intent |
|---|---|---|---|
| 1 | What is the status of my claim? | `CLM001010` | claim_status |
| 2 | When is my home insurance premium due? | `2026-09-01` | policy_status |
| 3 | What is my account balance? | `14,624` | account_balance_inquiry |
| 4 | What is my fixed deposit maturity amount? | `1,094,768` | account_balance_inquiry |

**Demo note.** One account is **below the minimum balance** (`Rs.2,507` against a `Rs.3,000`
requirement) and carries a `MinBalanceNonMaintenance` charge — a natural cross-sell/complaint hook.

---

## Hirithi Nandha — CRN00010004
**HNI · 26 months · hirithi.nandha@gmail.com**
Holds: Current account, RuPay Platinum, matured FD, Loan Against Property, Auto policy, 2 claims.

| # | Question | Expect | Intent |
|---|---|---|---|
| 1 | What is my loan status? | `LN001001` | loan_status |
| 2 | What is my credit card limit? | `Rs.830,000` | card_management |
| 3 | What is the status of my theft claim? | `CLM001011` | claim_status |
| 4 | When is my car insurance premium due? | `2027-04-15` | policy_status |

**Demo note.** The only customer holding **every** product type, so she exercises all five graph
paths. **All 4 questions were run end-to-end on 2026-08-12 and returned the correct record with
`retrieval_backend: neo4j_graph`.**

---

## Fathima Devasahayam — CRN00010005
**Affluent · 20 months · fathimawork511@gmail.com**
Holds: 2 savings accounts, Personal loan (EMI overdue), Term + Auto policies, 3 claims.

| # | Question | Expect | Intent |
|---|---|---|---|
| 1 | What is my loan status? | `LN001002` | loan_status |
| 2 | What is the status of my claim? | `CLM001015` | claim_status |
| 3 | When is my term insurance premium due? | `2026-07-02` | policy_status |
| 4 | What is my savings account balance? | `5,446` | account_balance_inquiry |
| 5 | There is an incorrect charge on my account | `TXN0001000067` | transaction_dispute |

**Demo note.** Her personal loan is **EMI overdue** and she has a **disputed** charge
(`CHG00100002`, `MinBalanceNonMaintenance`, `Rs.264.83`) — good material for the dispute and
attrition-risk stories.

---

## Knowledge-base questions (any customer)

These answer from the KB, not the graph — use them to show the **other** provenance branch.
All 14 FAQs are single-topic chunks after Fix 69; the five below were measured returning the
correct passage at rank 1 with a 1.9x-8.3x score gap over the runner-up.

| Question | Cited passage |
|---|---|
| How do I file a health insurance claim? | cashless: inform insurer/TPA within 24-48 hours |
| What is a Demat account? | electronic holding of securities for stock trading |
| How can I update my KYC details? | fresh identity + address proofs at the branch |
| What is the maximum daily ATM withdrawal limit? | typically Rs.10,000-Rs.50,000 for savings |
| Can I port my insurance policy to another insurer? | yes, at renewal, with continuity benefits |

Other indexed FAQs: opening a savings account, personal loan requirements, reporting a lost or
stolen card, applying for a home loan, SIP, ELSS tax benefits, term insurance, car insurance
premium factors, ULIP vs traditional plans.

---

## What to expect on escalation-type questions

Loan and claim questions usually classify **L2/L3**, so the review gate holds the reply: the
customer receives *"Support Agent will help you shortly…"* and the real answer waits as a draft
under **Needs Review**. This is the human-in-the-loop feature, not a failure.

Card, balance and premium questions typically auto-send.

**If you want a demo with no holds**, lead with card / balance / premium / FAQ questions. **If you
want to show human-in-the-loop**, lead with a loan or claim question and approve the draft on screen.

---

## Ticket continuity scenarios (the omnichannel story)

Everything above is a **single-turn question**, which proves answers are correct but shows nothing
about continuity — the thing that makes this an omnichannel system rather than a chatbot.

**Continuity does not require three channels to demonstrate.** Ticket matching keys on
`conversation_id` + `ticket_scope` (`ticket_manager.py`); the **channel is never part of the
matching logic**, only a label stored on the turn. So running a scenario entirely on web chat
exercises the identical code path a WhatsApp→email follow-up takes. Sending on a second channel
changes the dot colour in Lineage, not the behaviour being proven.

Run each scenario as consecutive messages from the SAME customer.

### Scenario A — vague opener, then specifics (scope refinement)
| Step | Message | Expected |
|---|---|---|
| 1 | I want to dispute a transaction on my account | Ticket created, scope `transaction_dispute:other` |
| 2 | It was the Rs.5,776 IMPS transfer to Samarth Thaker | **Same ticket**, scope refined — NOT a second ticket |
| 3 | Any update on my dispute? | **Same ticket** again (matched by the LLM referee) |

**Point at:** one ticket ID across all three exchanges in Lineage; the Detailed view showing three
exchanges under one request node.

### Scenario B — genuinely different matters must NOT merge
| Step | Message | Expected |
|---|---|---|
| 1 | I want to dispute a card transaction | Ticket A |
| 2 | I also have a problem with a UPI payment | **Ticket B** — a separate incident |

**Point at:** two distinct ticket IDs. This is the counter-example that proves the system is
matching rather than merging everything — worth showing right after Scenario A.

### Scenario C — topic switch inside one conversation
| Step | Message | Expected |
|---|---|---|
| 1 | What is my credit card limit? | Card theme, no ticket |
| 2 | When is my FD maturity date? | **Separate theme group**, no ticket |
| 3 | I want to dispute a transaction | Third theme, ticket created |

**Point at:** three theme headers in the Detailed view; the conversation stays one thread while the
topics are visibly separated.

**Verified end-to-end (2026-08-12, Fathima, real LLM).** A1+A2+A3 produced **one** ticket — including
A3 matching back to it despite classifying as a *different intent* (`ticket_status`) — and B1
correctly produced a **separate** ticket. Running these is what exposed Fix 72's two defects; they
did not pass before it.

**Both decisions are LLM judgement calls, so they are not bit-for-bit repeatable.** The bias is set
to merge when unsure on a vague ticket, and to fork when unsure elsewhere (a visible fork is fixable;
a silent merge hides a complaint). Rehearse once before demoing rather than assuming a given run
repeats.

**Known rough edge in Scenario A step 3:** the reply attaches to the right ticket but is still **held
for review**, so the customer sees the holding message rather than the status. Cause is in the
escalation rules, not continuity (Rule 0 escalates on an L2 classification before the
"ticket_status never escalates" rule is reached). If you demo A3, approve the draft on screen — or
lead with steps 1-2 only.

---

## Known gaps

- **Unverified senders** get "Dear Customer" and no graph data — by design (Fix 59/60).
- **In the graph but never read when answering:** `ChargePenalty` (7 nodes), `KYC` (5), `Product`
  (20, used by the offers engine only), `Interaction` (21, seeded history). No intent routes to
  them, so questions about a penalty charge or KYC status answer from the KB.
- **Dates in the seed are fixed and will age.** Sayantini's card payment due date (`2026-07-08`) is
  already past, and 3 of the 4 FDs are `Matured` with 2021-2023 dates. Answers are still correct
  about the record; they just describe the past.
- **Multi-account customers** (Sireesha, Digvijay have 2 savings accounts) get both accounts in a
  balance answer, with no way to disambiguate "my savings account" in a follow-up.
- The **Escalate** button is a UI stub — do not click it during a demo.
- `"scam"` does not match `"scammed"` (doubled-consonant inflections are not stemmed).
