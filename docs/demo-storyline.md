# Demo Storyline — one customer, one problem, eleven messages, three channels

**Sayantini Sarkar** · `CRN00010001` · Web Chat · WhatsApp `917890864700` · Email `sayantini.s.55@gmail.com`

Not eleven demos. **One problem, followed through** the way a real customer would raise it —
vaguely at first, then with detail, then with frustration, then from her phone the next day.

Every figure below was read from the live graph.

> **Pace: one message per minute.** ~5,700 tokens per message against an 8,000/min Groq limit.
> Two in a minute produces a rate-limit failure that dumps raw database text at the customer.

---

## The situation (all real, all in Neo4j)

Sayantini's Mastercard `CC00100001` is **45 days past due**. Rs.**91,821.95** outstanding,
minimum Rs.**4,591.10**, due date **2026-07-08**, interest **38.75%**. A late fee of Rs.**1,284.14**
(`CHG00100004`, *"Credit card payment overdue"*) was charged on **2026-07-01** and never reversed.

Separately, an IMPS transfer of Rs.**5,776.55** to **Samarth Thaker** on **2026-03-23**
(`TXN0001000003`) is still **Debited-Pending-Credit** — *"Beneficiary bank delayed crediting."*

**Her story:** she believes she paid the card using that transfer. The money left her account.
The bank never received it. So she is being charged a late fee for a payment she genuinely made.

That is a real bank complaint, and every element of it is in your data.

---

# ACT 1 — Routine, automatic (Web Chat)

*She starts where any customer starts: checking, not complaining.*

**1.** > What is my credit card outstanding?

→ Graph answers. **NO TICKET.** Should quote Rs.91,821.95, min Rs.4,591.10, due 2026-07-08.

**2.** > When is my next insurance premium due?

→ Different product, still routine. **NO TICKET.** Should quote **2026-10-23**, Rs.18,175.19.

**Say:** *"Two products, two systems of record, no human. She's just looking around — nothing
here needs a person, so nothing gets one."*

---

# ACT 2 — It becomes a problem (Web Chat, same conversation)

*The tone shifts, but watch WHAT escalates it.*

**3.** > Why have I been charged a late fee on my card?

→ Still a question. Graph names `CHG00100004`, Rs.1,284.14, 2026-07-01.
→ **Likely still NO TICKET** — she asked, the record answered.

**Say:** *"Still no human. She asked something we can answer."*

**4.** > But I already paid that. I sent Rs.5,776 by IMPS on 23 March and it left my account.

→ **This is the turn.** A disputed payment — `transaction_dispute`, MANUAL_REVIEW (Rule 2).
→ **TICKET CREATED. Reply HELD.** Customer sees *"Support Agent will help you with this shortly."*
→ The draft should find `TXN0001000003` and its *Debited-Pending-Credit* status.

**Say:** *"That escalated on content — she disputed money. Not on tone; she was perfectly polite."*

**5.** > This is the second time this has happened and honestly I'm losing patience.

→ Frustration, **no new facts**. Joins the existing ticket — **no second ticket**.

**Say (the important one):** *"Frustration did NOT create a ticket. Until today it would have —
we removed the rule that escalated on tone. 'URGENT' on a routine question is an anxious customer,
not an incident. This one was already with a human because of what she said in the previous
message."*

**6.** > Can someone actually look at this properly?

→ `human_escalation` — but a ticket already covers it. Still **one ticket**.

**→ NOW SWITCH TO THE AGENT VIEW.** Open the held draft. Show that the AI has already found the
transaction, the charge, and the dates. **Edit one line. Send.**

**Say:** *"The AI did the work — it found a March transaction and connected it to a July fee.
A person approved it. That's the split: machine does the finding, human owns the money decision."*

**Show:** the graph now records `HANDLED_BY → HUMAN_SR` and `EDITED_BY` if you changed the text,
while `drafted_by` still credits the AI.

---

# ACT 3 — Next day, different channel (WhatsApp)

*She's away from her desk. She doesn't repeat herself — and she shouldn't have to.*

**7.** From **917890864700**: > Any update on my complaint?

→ Identity resolves **by phone number** to the same `CRN00010001`. Different channel, different
conversation, fresh session.
→ Should **name the ticket from Act 2** and know it's about the late fee / stuck payment.
→ **NO NEW TICKET** — `ticket_status` is a lookup (Rule 3).

**Say:** *"New device, new channel, nothing re-explained. And note what she did NOT have to say —
no ticket number, no 'as I mentioned yesterday.'"*

**8.** > And has the Rs.5,776 come back yet?

→ A **specific follow-up on the same matter.** Should not fork a new ticket — the scope refinement
keeps it on the same case.

**9.** > What's my card outstanding now?

→ Back to routine, mid-complaint. **NO TICKET** — the open case doesn't make everything escalate.

**Say:** *"Notice: she has an open complaint AND just got an instant answer. Until today, a customer
with three open tickets asking a simple question got escalated for being unlucky. We removed that."*

---

# ACT 4 — Closing the loop (Email)

**10.** From **sayantini.s.55@gmail.com**: > Thanks — I can see the reversal now. Please close this.

→ Third channel, same case. Closure detected → **ticket CLOSED**.

**11.** *(optional)* > Actually, when is my premium due again?

→ Ticket is closed. The reply should answer the premium and **not** cite the closed ticket.

**Say:** *"A closed case stops being quoted. It stays in her history, but the system doesn't tell
her a finished matter is still open."*

---

## The whole arc

| | Messages | What it proves |
|---|---|---|
| **1** | 1-2 | Routine questions answered from her own records, instantly, no human |
| **2** | 3-6 | Escalation on **content, not tone** · frustration doesn't multiply tickets · AI drafts, human approves |
| **3** | 7-9 | Case follows the customer across channels · an open case doesn't block routine answers |
| **4** | 10-11 | Closure across a third channel · closed cases stop being cited |

**One ticket, eleven messages, three channels.**

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Raw `Loan records:` field=value text | **Groq 429.** Wait a minute, resend. Not a logic fault. |
| Message 3 creates a ticket | Acceptable — content rules judged it unanswerable. Say so honestly. |
| Message 5 or 6 creates a SECOND ticket | Report it — that is the ticket-continuity path failing. |
| Message 7 names no ticket | Act 2's ticket must still be **open**. |

## Do not demo
- **Live account balance** — no core-banking feed; returns the *average monthly* figure by design.
- **Jira sync** — credentials return 401.

## Before running
Consider a fresh start. She currently has **3 open tickets** from earlier testing
(`tkt_11e57833e42f` card, `tkt_5e0705a80b73` policy, `tkt_74137aabc75a` ticket-status) which will
appear in her open-cases list and clutter Act 2.
