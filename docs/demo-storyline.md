# Demo Storyline

**Sayantini Sarkar** — `CRN00010001` — HNI segment
Web Chat (portal) · WhatsApp `917890864700` · Email `sayantini.s.55@gmail.com`

One customer, one problem, nine messages, three channels, **one ticket**.

> **Pace: one message per minute.** Each message costs ~5,700 tokens against an 8,000/min Groq
> limit. Two inside a minute produces a rate-limit failure that sends raw database text to the
> customer. If you see `Recent transaction records:` field=value output, that is the rate limit —
> wait and resend.

---

## The problem (verified in Neo4j)

On **23 March 2026** Sayantini sent **Rs.5,776.55** to **Samarth Thaker** by IMPS
(`TXN0001000003`). The money left her account and never arrived.

The record still reads **`Debited-Pending-Credit`** — *"Beneficiary bank delayed crediting —
auto-reversal in progress."* It has been that way for over five months.

That is a genuine grievance with a real paper trail, and it is the spine of the demo.

**Two other transfers are also stuck**, which matters: her first vague message is genuinely
ambiguous, and the system has to work out which one she means.

| Txn | Date | Amount | To | Status |
|---|---|---|---|---|
| `TXN0001000003` | 2026-03-23 | **Rs.5,776.55** | Samarth Thaker | Debited-Pending-Credit |
| `TXN0001000014` | 2026-03-22 | Rs.5,220.47 | Kartik Kulkarni | Debited-Pending-Credit |
| `TXN0001000012` | 2026-03-18 | Rs.29,419.08 | Neelofar Kumar | Pending |

### Her other records (used in Acts 1 and 3)

| | |
|---|---|
| **Credit card** `CC00100001` | Mastercard Classic · balance **Rs.91,821.95** · min **Rs.4,591.10** · due **2026-07-08** · **45 days overdue** · late fee `CHG00100004` **Rs.1,284.14** charged 2026-07-01 |
| **Policy** `POL001001` | Health · Active · premium **Rs.18,175.19** · next due **2026-10-23** |
| **Claims** | `CLM001003` Under Review · `CLM001002` Approved · `CLM001001` Rejected |

> **The card and the transfer are unrelated.** The transfer went to a person in March; the card
> bill was due in July. Do **not** script her claiming she paid the card with it — the dates and
> the beneficiary both contradict it, and the system would be right while the script was wrong.

---

# ACT 1 — Routine questions, answered automatically
### Channel: **Web Chat**

*She starts by checking things. Nothing here needs a person.*

**1.** > When is my next insurance premium due?

Expect: **2026-10-23**, premium **Rs.18,175.19**. **`NO TICKET`.** Seconds.

**2.** > Why have I been charged a late fee on my card?

Expect: the fee explained *causally* — minimum **Rs.4,591** not paid by **08-Jul-2026** — plus her
balance **Rs.91,821** and how to pay. **`NO TICKET`.**

**Say:** *"Two products, two record systems, no human touched either. And the second one is not a
lookup — nothing in the database says WHY the fee was applied. It connected the fee, the minimum
payment and the due date into the answer she actually wanted."*

**Watch the sentiment badge — it reads `Concerned`. It still did not escalate.** Tone alone does
not create tickets. She asked something answerable, so it was answered.

---

# ACT 2 — A real problem reaches a human
### Channel: **Web Chat**, same conversation

**3.** > I sent money to someone by IMPS in March and it still has not reached them.

Vague — **three** of her transfers are stuck. Expect the system to surface the transaction(s) and
work out which matter this is.

**4.** > It was Rs.5,776 to Samarth Thaker on 23 March. It left my account and he never got it.

**This is the escalation.** A disputed payment → `transaction_dispute` → MANUAL_REVIEW (Rule 2).

Expect:
- Customer sees **"Support Agent will help you with this shortly"**
- **A ticket is created** — the only one in this demo
- The AI reply is **HELD**, not sent
- The draft should name `TXN0001000003`, Rs.5,776.55, 23-Mar-2026 and the
  *Debited-Pending-Credit* status

**Say:** *"That escalated on content — she disputed money that left her account. Not on tone.
She was perfectly polite."*

**5.** > It has been over five months. This is unacceptable.

Frustration, **no new facts**. Expect: **no second ticket** — it joins the existing one.

**Say (the point):** *"Frustration created nothing. Until today it would have — we removed the
rule that escalated on tone. An anxious customer is not a second incident. This was already with a
human because of what she said one message earlier."*

**→ SWITCH TO THE AGENT VIEW.** Open the held draft. Show that the AI has already found a
five-month-old transaction, its beneficiary and its failure reason. **Edit one line. Send.**

**Say:** *"The AI did the work. A person owns the money decision. That is the split."*

**Optionally show:** the graph records `HANDLED_BY → HUMAN_SR` (and `EDITED_BY` if you changed the
text), while `drafted_by` still credits the AI.

---

# ACT 3 — Next day, from her phone
### Channel: **WhatsApp** `917890864700`

*A different channel, a different conversation, a fresh session — and she does not repeat herself.*

**6.** > Any update on the transfer I raised yesterday?

Identity resolves **by phone number** to the same `CRN00010001`.

Expect: names **the ticket from Act 2**, knows it is about the Rs.5,776 IMPS transfer.
**NO NEW TICKET** — `ticket_status` is a lookup (Rule 3).

**Say:** *"New device, new channel, nothing re-explained. Note what she did NOT have to give: no
ticket number, no 'as I said yesterday.' The case follows the customer, not the window."*

**7.** > What is my credit card outstanding?

Routine, mid-complaint. Expect **Rs.91,821** and **`NO TICKET`**.

**Say:** *"She has an open dispute AND just got an instant answer. Until today, a customer with
open tickets asking a simple question was escalated for being unlucky. That rule is gone."*

---

# ACT 4 — Closing the loop
### Channel: **Email** `sayantini.s.55@gmail.com`

**8.** > I can see the reversal now. Please close the complaint.

Third channel, same case. Expect closure detected → **ticket CLOSED**.

**9.** > Thanks. When is my premium due again?

Expect: the premium answered, and **no mention of the closed ticket**.

**Say:** *"A closed case stops being quoted. It stays in her history; the system does not tell her
a finished matter is still open."*

---

## The arc

| Act | Messages | Channel | What it proves |
|---|---|---|---|
| 1 | 1-2 | Web Chat | Routine questions answered from her own records, instantly, no human |
| 2 | 3-5 | Web Chat | Escalates on **content, not tone** · frustration adds no ticket · AI drafts, human sends |
| 3 | 6-7 | WhatsApp | Case follows the customer across channels · an open case does not block routine answers |
| 4 | 8-9 | Email | Closure across a third channel · closed cases stop being cited |

**Nine messages · three channels · one ticket.**

---

## If something looks wrong

| Symptom | Meaning |
|---|---|
| Raw `Recent transaction records:` field=value text | **Groq 429.** Wait a minute, resend. Not a logic fault. |
| Message 3 escalates | Acceptable — a vague dispute is still a dispute. Act 2 just starts a message early. |
| Message 5 creates a **second** ticket | Report it — the ticket-continuity path is failing. |
| Message 6 names no ticket | Act 2's ticket must still be **open**. Check it was not closed early. |
| Message 2 creates a ticket | The graph lookup failed; the L2 gate correctly escalates when it cannot answer. |

## Before you start

- **Sayantini must have zero open tickets.** Act 2 should create the only one.
- **Do not demo:** live account balance (no core-banking feed — returns the *average monthly*
  figure by design) or Jira sync (credentials return 401).
