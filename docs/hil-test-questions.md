# HIL Manual Test — Questions

Manual human-in-the-loop (HIL) test scripts, one section per seeded customer. Send each message as
the **logged-in customer** so identity resolves to their real account.

Channels: **Web Chat** = portal "Chat with support" box · **WhatsApp** / **Email** = portal "Submit a request" form.

Customers covered:
- [Sayantini Sarkar](#customer-sayantini-sarkar) — `CRN00010001`
- [Fathima Devasahayam](#customer-fathima-devasahayam) — `CRN00010005`

---

# Customer: Sayantini Sarkar

`CRN00010001` · email `sayantini.s.55@gmail.com` · phone `7890864700`

## Group 1 — Guaranteed holds (creates a held draft every time)

| # | Channel | Message |
|---|---------|---------|
| 1 | Web Chat | There is an unauthorized transaction on my account and money is missing! |
| 2 | WhatsApp | My card was stolen and someone is making fraudulent charges. |
| 3 | Email | I think my account was hacked — I need this escalated urgently. |
| 4 | Web Chat | I received a phishing call and I shared my OTP by mistake. |

## Group 2 — Likely holds (may vary — small LLM classification)

| # | Channel | Message |
|---|---------|---------|
| 5 | WhatsApp | I want to increase my credit card limit. |
| 6 | Web Chat | I need to update my KYC documents. |
| 7 | Email | I want to dispute a transaction on my last statement. |
| 8 | Web Chat | Please transfer funds from my savings to my FD account. |

## Group 3 — Control (should NOT hold — auto-answers, no draft)

| # | Channel | Message |
|---|---------|---------|
| 9  | Web Chat | What are your customer support working hours? |
| 10 | WhatsApp | What is my credit card limit? |
| 11 | Web Chat | When is my FD maturity date? |

## Suggested run order

1. **#1 (Web Chat)** → see holding message → admin: edit & Send draft → back to portal, confirm reply appears (tests full flow + portal poll).
2. **#2 (WhatsApp)** → admin: Discard (tests discard path).
3. **#9 (Web Chat)** → confirms it auto-answers, no draft (selectivity).
4. **#5 (WhatsApp)** + **#6 (Web Chat)** → Needs-Review count → 2, both cards show L2 reasons.
5. **#4 (Web Chat)** → admin: Send → confirm portal poll delivers it.

---

# Customer: Fathima Devasahayam

`CRN00010005` · email `fathimawork511@gmail.com` · phone `7538870992`

**Her real holdings (used to ground the questions below):**
- **Accounts:** `40900000100007` (SA, avg bal ₹5,447) · `40900000100008` (SA, avg bal ₹1,721 — **below the ₹3,000 min**)
- **Personal Loan** `LN001002`: Active, outstanding ₹17,073, 1 EMI pending, **dpd 15**, overdue penalty ₹2,371
- **Policies:** Term Insurance `POL001007` (premium due **2026-07-02**) · Auto `POL001006`
- **Claims:** `CLM001015` Approved · `CLM001014` Under Review · `CLM001013` Processing (theft)
- **Charges:** e-NACH bounce ₹828 (Charged) · MinBalance non-maintenance ₹265 (**Disputed**)
- No credit card, no fixed deposit.

## Group 1 — Guaranteed holds (creates a held draft every time)

| # | Channel | Message |
|---|---------|---------|
| 1 | Web Chat | There is an unauthorized transaction on my account 40900000100007 and money is missing! |
| 2 | WhatsApp | My card was stolen and someone is making fraudulent charges. |
| 3 | Email | I think my account was hacked — I need this escalated urgently. |
| 4 | Web Chat | I received a phishing call and I shared my OTP by mistake. |

## Group 2 — Likely holds (may vary — small LLM classification)

| # | Channel | Message |
|---|---------|---------|
| 5 | WhatsApp | I want to dispute the ₹828 e-NACH bounce charge on account 40900000100007. |
| 6 | Web Chat | I need to update my KYC documents. |
| 7 | Email | My minimum balance penalty on account 40900000100008 is unfair — please reverse it. |
| 8 | Web Chat | I want to reschedule the overdue EMI on my Personal Loan LN001002. |

## Group 3 — Control (should NOT hold — auto-answers, no draft)

| # | Channel | Message |
|---|---------|---------|
| 9  | Web Chat | What are your customer support working hours? |
| 10 | WhatsApp | What is the status of my Personal Loan LN001002? |
| 11 | Web Chat | When is the next premium due on my Term Insurance policy? |
| 12 | Email | What is the current balance of my savings account 40900000100007? |

## Suggested run order

1. **#1 (Web Chat)** → see holding message → admin: edit & Send draft → back to portal, confirm reply appears (tests full flow + portal poll).
2. **#2 (WhatsApp)** → admin: Discard (tests discard path).
3. **#10 (WhatsApp)** → confirms it auto-answers her real loan status, no draft (selectivity + grounded data).
4. **#5 (WhatsApp)** + **#7 (Email)** → Needs-Review count → 2, both cards show her real charge/penalty references.
5. **#4 (Web Chat)** → admin: Send → confirm portal poll delivers it.

> Note: Group 2 outcomes depend on the small LLM's per-query L1/L2/L3 call and can vary between runs. Group 3 assumes the customer's seeded data is present (verify with the admin Profile Snapshot if a control question unexpectedly holds).
