# Demo Practice Script — grounded in the freshly reseeded data (2026-07-27)

Built against the **5 real BFSI customers** now in Neo4j after the fresh start. Every question below
resolves against actual seeded data, so the AI gives a real, specific answer (not a generic hedge).

> **Before you rehearse:** send ONE real WhatsApp from your Meta-verified number and confirm the reply
> lands on the phone — that's the only test that proves ngrok → webhook → Groq → Neo4j → KB → Meta all
> work together. Everything else is verified.

> **Quota note:** each conversation burns Groq tokens (`opportunity_generation` is the heaviest).
> ~100+ conversations/day of headroom, but don't spray — rehearse the flows you'll actually show.

---

## The 5 customers (real seeded data)

| Customer | Segment | Phone | Email | Notable holdings |
|---|---|---|---|---|
| **Sayantini Sarkar** | HNI | 7890864700 | sayantini.s.55@gmail.com | Mastercard Classic (limit ₹10,65,000, **dpd 45 — overdue**, due 2026-07-08, ₹91,821 due, late fee applied), FD ₹1,60,000 (matures 2028-01-12), Health policy |
| **Hirithi Nandha** | HNI | 9150697784 | hirithi.nandha@gmail.com | RuPay Platinum (limit ₹8,30,000, ₹4,38,526 due), Loan Against Property (Active), FD, Auto policy |
| **Digvijay Yadav** | Affluent | 7700920746 | digvijayyadav48@gmail.com | FD, Home Insurance policy, 2 accounts |
| **Fathima Devasahayam** | Affluent | 7538870992 | fathimawork511@gmail.com | Personal Loan (Active), 2 policies, 3 claims |
| **Sireesha** | Mass Affluent | 9398314492 | s.sireesha28092004@gmail.com | 1 card, FD, 2 policies, 4 claims |

Use the **phone** to message from WhatsApp; the **email** to send an email; or log into the customer
portal (web chat) as that customer.

---

## Flow 1 — L1 lookup, NO ticket (the "AI just answers" moment)

These resolve from graph/KB data and should NOT create a ticket or a held draft — they auto-send.

- *(as Sayantini, WhatsApp)* **"What is my credit card limit?"** → ₹10,65,000, auto-answered.
- *(as Sayantini)* **"When does my fixed deposit mature?"** → 2028-01-12.
- *(as Hirithi)* **"What's the outstanding balance on my credit card?"** → ~₹4,38,526.
- *(any customer)* **"What are your customer-support hours?"** → answered from the KB, no ticket.

**What to point at:** reply auto-sends, no "Needs Review" badge, no ticket in the right panel.

---

## Flow 2 — L2 / L3 escalation → held-reply draft (human-in-the-loop)

These require a ticket, so the customer gets a holding message and the AI's answer is **held as an
editable draft** for the agent. This is the flagship feature.

- *(as Sayantini)* **"I want to increase my credit card limit."** → L2, ticket + held draft.
- *(as Hirithi)* **"There's a transaction on my card I don't recognise — I think it's fraud."** → L3
  critical, ticket + held draft.
- *(as Fathima)* **"I want to dispute a charge on my personal loan penalty."** → L2/L3, held.

**What to point at:**
1. Customer receives the **holding message** ("Support Agent will help you with this shortly…").
2. Admin inbox shows the **"Needs Review"** filter + amber badge.
3. Open the conversation → the **held-reply draft card** with the AI's proposed answer, the
   escalation-reason label, and the **confidence pills** (retrieval + intent).
4. **Edit** the draft, click **Send** → the real reply is delivered and the holding message is replaced.

---

## Flow 3 — Cross-channel ticket continuity

Show a ticket opened on one channel and followed up on another — it should refine the SAME ticket, not
fork a duplicate.

- *(as Sayantini, WhatsApp)* **"I want to raise a dispute about a charge."** → opens a dispute ticket.
- *(then as Sayantini, EMAIL)* **"Any update on my dispute?"** → the tier-4 LLM referee matches it to
  the open ticket instead of creating a second one.

**What to point at:** the **Lineage** view — the dispute shows as one ticket with dots across both
WhatsApp and email channels, oldest→newest.

---

## Flow 4 — Suggested Offers (cross-sell / up-sell)

Sayantini is HNI with an entry-level Classic card → a natural card-upgrade offer. (Note: her card is
dpd 45, so the dpd<30 guard on the HNI-upgrade rule may suppress it — good honesty moment, or use
Hirithi who is dpd 0 for a cleaner offer.)

- *(as Hirithi, whose card is current)* ask a **positive/neutral** product question, e.g.
  **"What benefits does my platinum card give me?"** → after answering, the **Suggested Offers** card
  appears in the right panel.

**What to point at:**
1. The **Suggested Offers** card (purple heading) with the LLM-written pitch.
2. **Approve** → an editable offer draft.
3. **Send** → delivered to every push channel on record (deduped, so no double-send).
4. The offer turn renders as a **"Bank-initiated / Offer Message"** row (Detailed) / amber Offer dot
   (Lineage) — never a blank reply row.

> Gate: if the customer's latest message is **negative**, offers are suppressed ("No offers right
> now"). Keep the lead-in message positive to make the offer show.

---

## Flow 5 — Right-panel customer intelligence

Open any customer (Sayantini is richest) and walk the right panel:

- **Attrition risk** band — Sayantini should read **Medium/High** (dpd 45 overdue card is a strong
  sign). Explain it's a transparent rule-based heuristic, not a black-box prediction.
- **Tenure · Segment · Deadline** tiles — the Deadline tile surfaces her overdue card payment.
- **Sentiment (last 5 messages)** — shifts as you send frustrated vs neutral messages.
- **Open Tickets (N)** card — appears only when something is open.

---

## Flow 6 — Analytics page (Digvijay's merged work + the redesign)

Navigate to Analytics and show:

- **FinOps / LLM observability** — KPI tiles (hover for the formula tooltip), operations meter bars,
  cost/latency-per-call by model+version comparison strips, and the **hourly cost/tokens line charts**
  (IST-bucketed).
- **Customer Care** — Tickets by channel (real channels only, no fake `graph`/`portal`), top intent
  trends, agent/team performance.
- **Solution Performance** — Escalation rate (escalated tickets ÷ inbound queries), Avg risk score,
  Critical load, Drafts handled; plus "Open tickets by risk band" + "Why tickets escalate" charts.

> The LLM-version tag (`v-xxxx`) only appears on NEW LLM calls made after the fresh start — the panel
> will populate as you run rehearsal conversations.

---

## Flow 7 — Unregistered-customer rejection (the guard)

Show that a NON-seeded customer gets cleanly rejected on account-specific questions.

- *(from a number/email NOT in the 5 above)* **"What is the status of my personal loan?"** → clean
  "We couldn't verify your account…" rejection: **no name, no ticket, no fabricated data.**
- *(same unknown user)* **"What is my credit card limit and current balance?"** → same clean
  rejection — no invented ₹ figure, no phantom card, no name in the greeting ("Dear Customer").
- *(same unknown user)* **"I think there's a fraudulent transaction on my account — please block it."**
  → account-specific + high-risk, but still rejected (no ticket, no fake account); proves the guard
  runs BEFORE escalation, so an unverified user can't force a ticket via fraud language.
- *(same unknown user)* a **general** question ("What are your support hours?") → still answered
  (general KB is open to anyone).

---

## Suggested 5-minute demo path (if time is tight)
1. Sayantini WhatsApp: "What's my card limit?" → instant real answer (Flow 1).
2. Sayantini: "I want to increase my limit" → held draft; edit + send it (Flow 2).
3. Cross-channel follow-up on email → one ticket, not two (Flow 3).
4. Right panel: attrition Medium/High + overdue deadline (Flow 5).
5. Analytics page skim (Flow 6).
