# Demo Scenarios — Sayantini, Digvijay, Fathima

Every fact below was read from Neo4j. Where two records connect, the link was **checked**, not
assumed — the joining field is named so you can verify it yourself.

> **Pace: one message per minute.** ~5,700 tokens per message against an 8,000/min Groq limit.
> Raw `field=value` output on screen means the rate limit, not a logic fault.

---

# FATHIMA DEVASAHAYAM · `CRN00010005` · Affluent
### The strongest scenario — one cause, four consequences

**The chain, all on account `40900000100007`:**

| | |
|---|---|
| Account `…007` holds | Rs.5,446.92 · minimum required **Rs.3,000** |
| Loan `LN001002` | Personal Loan · repaid from **that same account** · **53 of 54 EMIs paid** |
| On **2026-05-05** | e-NACH auto-debit **bounced** — `CHG00100003`, **Rs.828.26**, *"insufficient funds"* |
| Consequence | Loan now **15 days past due** · penalty **Rs.2,371** · *"EMI overdue — reminder sent"* |
| Her other account `…008` | Rs.1,720.52 — also below minimum · `CHG00100002` **Rs.264.83**, status **Disputed** |

**Why this is the best scenario you have:** a customer who has paid **53 of 54 instalments**
misses the last one because an auto-debit bounced. She is not a defaulter — she is one payment
from clearing a Rs.8.7 lakh loan, and the bank has charged her twice and marked her overdue.

**And the link is real:** the bounce charge and the loan carry the same `account_number`. Verified.

### Scenario A — "Why am I being charged twice?"

1. `Why have I been charged Rs.828 on my account?`
2. `But my loan EMI is on auto-debit. Why did it bounce?`
3. `I have paid 53 out of 54 EMIs. Now you are charging me a penalty on the last one?`
4. `And there is another charge of Rs.264 on my other account. I have already disputed that one.`
5. `Can someone sort this out properly?`

**Expect:** 1-2 answered instantly. 3 or 4 escalates — a disputed charge on money.
`CHG00100002` is **already marked Disputed** in the graph, so the system should recognise it.

### Scenario B — the last EMI

1. `What is my loan status?`
2. `How much is left on it?`
3. `Why is it showing overdue when I have an auto-debit set up?`
4. `I want the penalty reversed — the bounce was not my fault.`

**Expect:** 1-3 answered from the graph. 4 escalates — a reversal request is a money decision.

### Also true for her
- Term policy `POL001007` premium was due **2026-07-02** — two months ago
- Auto policy `POL001006` due 2026-09-12
- Claims: `CLM001015` Approved (Rs.1,52,385 of Rs.1,88,904) · `CLM001014` Under Review ·
  `CLM001013` Theft, Processing
- Stuck: `TXN0001000067` Rs.28,991.63 to Kimaya Seth, 23-Jun, **Pending** ·
  `TXN0001000058` Rs.5,188.46 to Hansh Bir, 22-Mar, **Failed**

---

# DIGVIJAY YADAV · `CRN00010003` · Affluent
### Two clean scenarios — no card, so nothing card-related

**His records:**

| | |
|---|---|
| Accounts | `…005` Rs.14,624.24 · `…004` **Rs.2,507.81** — below the Rs.3,000 minimum |
| Charge | `CHG00100001` **Rs.658.56**, 2026-04-14, *"Average monthly balance below required minimum"* |
| Home policy `POL001004` | Active · premium **Rs.19,355.21** · **next due 2026-09-01 — today** |
| Claims | `CLM001008` Approved (Rs.4,07,292 of Rs.5,08,748) · `CLM001009` **Rejected** (Rs.4,97,729) · `CLM001010` Processing (Rs.1,81,919) |
| Stuck | `TXN0001000045` Rs.41,223.59 to Romil Halder, 12-Jan, **Debited-Pending-Credit** · `TXN0001000044` Rs.13,055.06 ATM, 19-Feb, **Failed** |

### Scenario C — the rejected claim *(his strongest)*

1. `What is the status of my home insurance claims?`
2. `Why was my claim for Rs.4,97,729 rejected?`
3. `You approved a similar claim before this one. Why was this one turned down?`
4. `I want this reviewed. That is nearly five lakhs.`

**Expect:** 1-2 answered. 3 is the interesting one — **two structural-damage claims, one approved
at Rs.4,07,292 and one rejected**, both real. 4 escalates.

> The graph holds no `rejection_reason` (it is NULL). If the reply says it cannot see the reason,
> **that is correct behaviour** — it should not invent one. Worth calling out as a strength.

### Scenario D — the ATM that failed

1. `Rs.13,055 was debited at an ATM on 19 February but I did not get the cash.`
2. `It has been over six months.`
3. `Also, Rs.41,223 I sent to Romil Halder in January never reached him.`

**Expect:** 1 escalates immediately — a failed ATM debit is a disputed transaction. 3 is a
**second, different** matter; watch whether it joins the ticket or opens its own. Either is
defensible; note which happens.

### Scenario E — the minimum-balance charge

1. `Why was I charged Rs.658?`
2. `My other account has Rs.14,000 in it. Why can you not look at them together?`

**Expect:** 1 answered from the charge record. 2 is a policy question — likely a KB answer or an
escalation. **Both accounts are real and the balances are as stated.**

---

# SAYANTINI SARKAR · `CRN00010001` · HNI
### Three scenarios — keep them separate

> **Her card and her stuck transfer are NOT connected.** The transfer went to a *person* by IMPS
> on **23 March**; the card bill was due **8 July**. Do not script her claiming she paid the card
> with it — the dates and the beneficiary both contradict it.

**Her records:**

| | |
|---|---|
| Card `CC00100001` | Mastercard Classic · balance **Rs.91,821.95** · min **Rs.4,591.10** · due **2026-07-08** · **45 days overdue** · late fee `CHG00100004` **Rs.1,284.14** on 2026-07-01 |
| Account `…001` | Rs.0 average monthly balance |
| Policy `POL001001` | Health · premium **Rs.18,175.19** · due **2026-10-23** |
| Claims | `CLM001002` Approved (Rs.1,15,548 of Rs.1,46,082) · `CLM001003` Under Review (Rs.2,24,755) · `CLM001001` **Rejected** (Rs.96,400) |
| Stuck | `TXN0001000003` **Rs.5,776.55** Samarth Thaker 23-Mar **Debited-Pending-Credit** · `TXN0001000014` Rs.5,220.47 Kartik Kulkarni 22-Mar same · `TXN0001000012` Rs.29,419.08 Neelofar Kumar 18-Mar **Pending** |

### Scenario F — the vanished transfer *(her strongest)*

1. `I sent money by IMPS in March and it still has not reached the person.`
2. `It was Rs.5,776 to Samarth Thaker on 23 March.`
3. `It has been over five months. This is unacceptable.`
4. `Any update on this?`  ← **send from WhatsApp `917890864700`**

**Expect:** 1 is genuinely ambiguous — **three** of her transfers are stuck, so the system has to
work out which. 2 escalates: a disputed payment. 3 adds frustration and **no new facts** — it
should add **no second ticket**. 4 on WhatsApp should name the ticket from message 2.

### Scenario G — the overdue card

1. `Why have I been charged a late fee on my card?`
2. `What is my outstanding?`
3. `Can I pay just the minimum?`

**Expect:** all three answered instantly, **no ticket**. Note the sentiment badge reads
`Concerned` and it *still* does not escalate — tone alone no longer creates tickets.

Message 1 is the best single answer in the demo: **nothing in the database says why the fee was
applied.** The system connects the fee, the unpaid minimum and the due date itself.

### Scenario H — the rejected health claim

1. `Why was my hospitalisation claim rejected?`
2. `You approved my other claim for Rs.1,15,548. Why not this one?`
3. `I want it looked at again.`

**Expect:** 1-2 from the graph, 3 escalates. Same shape as Digvijay's Scenario C — and the same
honest limitation: no `rejection_reason` is stored, and the system should say so rather than
invent one.

---

## Which to use

| Want to show | Use |
|---|---|
| **One cause, many consequences** | **Fathima A** — the bounce that caused the overdue |
| **Cross-channel continuity** | **Sayantini F** — message 4 arrives on WhatsApp |
| **Escalates on content, not tone** | **Sayantini F** msg 3, or **G** with its `Concerned` badge |
| **Honest about what it does not know** | **Digvijay C** or **Sayantini H** — no rejection reason stored |
| **Two separate matters at once** | **Digvijay D** — ATM failure plus an unrelated stuck transfer |

## Before you start
- The customer must have **zero open tickets** if you want the scenario to create the only one.
- **Do not demo:** live account balance (no core-banking feed) or Jira sync (401).
