# HIL Manual Test — Questions for Sayantini Sarkar

Customer: **Sayantini Sarkar** · `CRN00010001` · email `sayantini.s.55@gmail.com` · phone `7890864700`
Send each as the logged-in customer so identity resolves to her real account.

Channels: **Web Chat** = portal "Chat with support" box · **WhatsApp** / **Email** = portal "Submit a request" form.

---

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

---

## Suggested run order

1. **#1 (Web Chat)** → see holding message → admin: edit & Send draft → back to portal, confirm reply appears (tests full flow + portal poll).
2. **#2 (WhatsApp)** → admin: Discard (tests discard path).
3. **#9 (Web Chat)** → confirms it auto-answers, no draft (selectivity).
4. **#5 (WhatsApp)** + **#6 (Web Chat)** → Needs-Review count → 2, both cards show L2 reasons.
5. **#4 (Web Chat)** → admin: Send → confirm portal poll delivers it.
