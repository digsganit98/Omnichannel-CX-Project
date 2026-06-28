# Phase 2 — KB Verification Eval Set

Pass/fail target for verifying the 9 new markdown KB files end-to-end (OpenSearch
index + retrieval + answer + escalation behaviour). Defined BEFORE running so results
are judged against a fixed bar, not rationalised after the fact.

## RESULT — run 2026-06-28 (Docker stack, 66 docs indexed): ALL SETS PASS

- **Positive: 10/10** — every question retrieved its target file (R) and gave the key fact (A). (P1/P3 looked like A-misses only due to answer truncation in the test harness; full answers were correct.)
- **Regression: 2/2** — G1 (savings account) and G2 (SIP) still retrieve the original `InboxIQ_BFSI_KB.pdf`; not buried by the new files.
- **Negative: 5/5** — transaction_dispute, fraud_report, account_balance, human_escalation, complaint all still escalate (verified against the real `_escalation_reason` logic, even with high-confidence KB context). WhatsApp simulator transport not exercised (disabled via `WHATSAPP_LOCAL_TEST_MODE=false`); the escalation logic it would call is what was tested.

## How to run (requires Docker stack up)

1. `docker compose up --build -d` (API, OpenSearch, Ollama, Neo4j).
2. Re-index: `POST /admin/rag/index?recreate=true` with header `x-admin-key: <ADMIN_API_KEY>`.
   Expect `documents_loaded` to reflect PDF + 9 markdown files (66 chunks at time of writing).
3. For each question, send it through a channel (WhatsApp/email simulator or `/admin/rag/query`)
   and inspect the response JSON: `rag_contexts` / `citations` (retrieval), the answer text,
   and `ticket_id` / `outbound` (escalation).

## Pass criteria (per question)

- **R (Retrieval):** a chunk from the intended file appears in `rag_contexts` / `citations`.
- **A (Answer):** reply contains the key fact (not a generic deflection). Soft criterion —
  answer wording depends on Groq; if the Groq key is absent, A may degrade even when R passes.
- **E (Escalation):** for POSITIVE cases, **no ticket** is created. For NEGATIVE cases, the
  system **does** escalate / does not fabricate account data.

**Hard gate = R + E.** A is graded as a quality signal only.

## Overall bar

- **POSITIVE set PASS** = ≥ 8 of 10 positive questions pass R + E.
- **REGRESSION set PASS** = both old-PDF cases (G1, G2) still retrieve a PDF chunk.
- **NEGATIVE set PASS** = all negative cases still escalate / refuse (these must not regress).
- Overall KB verification PASS requires all three sets to pass.
- **< 8/10 positive, or a regression miss** → investigate `RAG_TOP_K` (currently 4, vs 66
  chunks), chunk ranking, or the rerank/escalation thresholds (`_should_prefer_local_context`
  0.35; Rule 8 conf 0.3).

## Positive cases (KB should answer, should NOT escalate)

| # | Question | Target file | Key fact in answer |
|---|----------|-------------|--------------------|
| 1 | How do I register a new payee, and why can't I send the full amount immediately? | how_to_procedures | beneficiary cooling-off / lower initial limit |
| 2 | What's the charge if my cheque bounces? | fees_and_charges | ~₹300–500 cheque return charge |
| 3 | Is there a penalty for prepaying my home loan? | fees_and_charges | floating-rate retail loans → no foreclosure charge (RBI) |
| 4 | Someone called asking for my OTP to verify my account — is that the bank? | fraud_and_security | bank never asks for OTP/PIN/CVV; it's fraud |
| 5 | The bank didn't resolve my complaint. Where do I escalate? | grievance_redressal | RBI Ombudsman / RB-IOS (after ~30 days) |
| 6 | Do senior citizens get a higher FD rate? | interest_rates | +~0.50% p.a. for senior citizens |
| 7 | What's the eligibility for your business loan? | product_eligibility | vintage > 3 yrs, turnover ₹10 lakh |
| 8 | Are my deposits insured if the bank fails? | regulatory_faqs | DICGC ₹5 lakh per depositor per bank |
| 9 | What does the first digit of my card number mean? | bank_reference | 4=Visa, 5=Mastercard, 6=RuPay, 3=Amex |
| 10 | What are typical branch working hours? | branch_atm_directory | 10–4 weekdays, half-day/closed Saturdays |

## Regression cases (old PDF KB must STILL be retrievable)

With 66 chunks now (was ~9) and `RAG_TOP_K=4`, a new markdown chunk could crowd out an
original-PDF answer. These confirm the pre-existing `InboxIQ_BFSI_KB.pdf` content was not
buried or displaced by the new files. Pass = R (a PDF chunk is retrieved) + A (correct fact)
+ E (no wrongful escalation).

| # | Question | Target file | Key fact in answer |
|---|----------|-------------|--------------------|
| G1 | How do I open a new savings account? | InboxIQ_BFSI_KB.pdf | branch visit + valid ID (Aadhaar/PAN/passport) + address proof; video-KYC option |
| G2 | What is SIP (Systematic Investment Plan)? | InboxIQ_BFSI_KB.pdf | fixed amount invested regularly into a mutual fund; rupee-cost averaging |

A regression case FAILS if no PDF chunk is retrieved for these topics (i.e. the new markdown
files displaced the original content).

## Negative cases (must STILL escalate or refuse — no regression)

These verify the new KB did NOT make the bot over-confident on things that must reach a human
or that the system has no data for. Each must NOT be silently "answered away".

| # | Question | Expected behaviour | Why |
|---|----------|--------------------|-----|
| N1 | There is a transaction on my account I did not make. | Escalate (ticket). | transaction_dispute ∈ MANUAL_REVIEW_INTENTS (Rule 2). |
| N2 | I want to report fraud / my card was used by someone. | Escalate (ticket) to fraud team. | fraud_report ∈ MANUAL_REVIEW_INTENTS. |
| N3 | What is my current account balance? | Escalate / no fabricated number. | account_balance_inquiry → Rule 2b no_live_banking_data (no banking data exists). |
| N4 | I want to speak to a human agent. | Escalate (ticket). | human_escalation (Rule 1). |
| N5 | I want to file a complaint — your service is unacceptable. | Escalate (ticket) to customer care. | complaint ∈ MANUAL_REVIEW_INTENTS. |

A negative case FAILS if the bot answers it confidently from the KB and creates no ticket
(for N1/N2/N4/N5) or invents a balance (N3).
