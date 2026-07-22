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

## Group 4 — Cross-sell / Up-sell opportunities (admin "Opportunities" card)

Her holdings: Classic card (₹10.65L limit, **dpd 45**), CSA account (bal 0/min 0), FD `FD001001`
(matures 2028 — outside the 90-day window), **Health policy**, **no loans**. Charges on file:
AnnualFee + LateFee totalling **₹3,791** (rule 9 trigger). Offers already suggested for a
conversation are never re-suggested (pending/approved/dismissed all count), so items below marked
*(one-shot)* only appear the first time.

| # | Portal message (Web Chat) | Rule it triggers | Expected in admin Opportunities card |
|---|---------------------------|------------------|--------------------------------------|
| 12 | What are your personal loan interest rates? I'm thinking about applying | Rule 10 — asked about loans, holds none *(one-shot; already consumed in the 2026-07-23 test run)* | **Cross-sell** "personal loan" pitch, Why: *customer asked about loans in chat, holds none* |
| 13 | *(no message needed — from her existing charges)* | Rule 9 — 2 unreversed charges ₹3,791 | **Up-sell** "waive INR 3,791 in charges" *(one-shot)* |
| 14 | This bank is useless, nothing ever works! | **Sentiment gate** | Card shows *"No opportunities right now — recent negative sentiment"* (send a neutral message after to un-gate) |
| 15 | Do you offer term life insurance plans? | Rule 10 — policy family, but she **holds** a Health policy | **Nothing fires** (family counts as held) — documents the known coarse-family limitation |

**Approve flow (either offer):** Approve → green "💡 Approved offer" draft card → edit → Send offer →
delivered to **email only** for her (no WhatsApp identity on her portal signup) → 1 outbound turn +
Mailpit mail "An offer curated for you". If she replies to that email, the reply lands in the same
conversation and the offer + reply render inside ONE request row (offer-glue grouping).

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

## Group 4 — More scenarios (extra coverage across her real holdings)

Grounded in Fathima's seeded data above, to give the Lineage / theme views more
requests across more themes. Group tags below mirror Groups 1–3 (hold vs. control),
but Group-2-style items can vary with the small LLM's per-query level call.

| # | Channel | Message | Grounds on | Expected |
|---|---------|---------|-----------|----------|
| 13 | Web Chat | What is the status of my theft claim CLM001013? | Claim `CLM001013` (Processing, theft) | Control — auto-answer |
| 14 | WhatsApp | Why is my claim CLM001014 still under review? | Claim `CLM001014` (Under Review) | Likely hold (L2) |
| 15 | Email | My approved claim CLM001015 hasn't been paid out yet — please check. | Claim `CLM001015` (Approved) | Likely hold (L2) |
| 16 | Web Chat | I want to file a new claim on my auto policy POL001006. | Auto policy `POL001006` | Likely hold (L2) |
| 17 | WhatsApp | Please reverse the ₹265 minimum balance penalty on account 40900000100008 — it's already disputed. | MinBalance charge ₹265 (**Disputed**) · acct `…008` | Likely hold (L2) |
| 18 | Email | The overdue penalty of ₹2,371 on my loan LN001002 is too high — can you waive it? | Loan `LN001002` penalty ₹2,371 | Likely hold (L2) |
| 19 | Web Chat | I want to close my savings account 40900000100008. | Account `…008` (below-min) | **Guaranteed hold** (exit language) |
| 20 | WhatsApp | I'm thinking of switching banks — nothing here works for me. | — (exit language) | **Guaranteed hold** (attrition High) |
| 21 | Web Chat | What is the average monthly balance on my account 40900000100008? | Account `…008` (avg ₹1,721) | Control — auto-answer |
| 22 | Email | How many pending EMIs do I have on Personal Loan LN001002? | Loan `LN001002` (1 EMI pending, dpd 15) | Control — auto-answer |

## Group 5 — Cross-sell / Up-sell opportunities (admin "Opportunities" card)

Fathima is the **richest opportunity customer**: no credit card, no FD, no health policy,
2 real charges (e-NACH bounce ₹828 Charged + MinBalance ₹265 Disputed — both count as
unreversed for rule 9). Gate: her **latest** message must not be negative — several Group 1/2/4
messages are, so send a neutral/positive message first (e.g. #23) if the card shows the
sentiment-suppressed state. Remember offers are one-shot per conversation.

| # | Portal message (Web Chat) | Rule it triggers | Expected in admin Opportunities card |
|---|---------------------------|------------------|--------------------------------------|
| 23 | Thanks, that's all sorted now. By the way, how do I apply for a credit card? | Rule 10 — `card_management`, holds no card (+ clears the sentiment gate) | **Cross-sell** credit-card pitch, Why: *customer asked about credit cards in chat, holds none* |
| 24 | *(no message needed — from her data)* | Rule 2 — no health policy | **Cross-sell** health insurance *(one-shot)* |
| 25 | *(no message needed — from her data)* | Rule 3 — active accounts, no credit card | **Cross-sell** credit card *(one-shot; may merge with #23's — one candidate per product)* |
| 26 | *(no message needed — from her data)* | Rule 9 — 2 unreversed charges ₹1,093 | **Up-sell** charge-waiver account tier *(one-shot)* |
| 27 | Everything is broken and nobody helps me here! | **Sentiment gate** | *"No opportunities right now — recent negative sentiment"* until her next neutral message |

The LLM shows at most **2** items at a time, prefers ones tied to the recent conversation, and may
phrase pitches differently per run (wording is non-deterministic; product + "Why" grounding are not).
**⚠ Send caution:** approving + sending for Fathima delivers to her real email
`fathimawork511@gmail.com` AND her WhatsApp identity if one exists — with local SMTP (Mailpit) and
the local WhatsApp test adapter nothing leaves the machine, but verify `OUTBOUND_DELIVERY_MODE`
before sending offers to her on a non-local setup.

## Suggested run order

1. **#1 (Web Chat)** → see holding message → admin: edit & Send draft → back to portal, confirm reply appears (tests full flow + portal poll).
2. **#2 (WhatsApp)** → admin: Discard (tests discard path).
3. **#10 (WhatsApp)** → confirms it auto-answers her real loan status, no draft (selectivity + grounded data).
4. **#5 (WhatsApp)** + **#7 (Email)** → Needs-Review count → 2, both cards show her real charge/penalty references.
5. **#4 (Web Chat)** → admin: Send → confirm portal poll delivers it.
6. **#13–#16** → build up her Claims / Insurance themes so the Lineage view shows multiple requests per theme.
7. **#19 or #20** → exit language → confirm the Attrition-risk band flips to **High** in the Profile Snapshot.
8. **#23 (Web Chat)** → open her conversation in admin → Opportunities card shows 1–2 items (credit card / health insurance / charge waiver) → Approve one → Send offer → confirm the offer turn(s) + the Offer-labelled row in Lineage/Detailed.

> Note: Group 2 outcomes depend on the small LLM's per-query L1/L2/L3 call and can vary between runs. Group 3 assumes the customer's seeded data is present (verify with the admin Profile Snapshot if a control question unexpectedly holds).
