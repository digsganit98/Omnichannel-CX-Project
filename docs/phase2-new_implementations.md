# Phase 2 — New Implementations

A running record of every change made during Phase 2 work, on top of the Phase 1
baseline. Newest entries at the bottom of each section.

> Baseline: the repo as of branch `Sayantini-phase2` is treated as Phase 1.
> Charter: see [`phase2-plan.md`](phase2-plan.md).
> Principles: additive-first (don't break Phase 1); synthetic data is acceptable;
> same database (`cx_phase1.db`); new migrations sequential from `006_`.

## Design decisions (Group B — missing per-customer/reference data)

- **Per-customer BFSI data (items 12,15,16,17,18) → Neo4j**, NOT SQLite. The parent
  entities (`:Loan`, `:Policy`) live in the graph and the resolution path (`neo4j_answer()`
  via `get_loan_status`/`get_claim_status`/`get_policy_status`) reads the graph. Putting
  child data in SQLite would orphan it from the answer path and depends on the unresolved
  migrate-on-startup gap (and SQLite has no auto-seed). Graph keeps it in one store, served
  by extending the existing queries. (This reverses an earlier "R1 SQLite migrations" idea.)
- **Reference data (items 13 network providers, 14 claim docs/SLA) → KB markdown**, reusing
  the Group A pipeline — it is FAQ-shaped, not per-customer.
- **Storage shape = summary PROPERTIES on the parent node** (option a), not full child-node
  tables. Stores headline facts that answer chat intents (next EMI, outstanding, foreclosure,
  arrears, premium next-due) — not exhaustive amortization rows. Full tables can be added
  later if a "download schedule" feature ever needs them (not a one-way door).
- Same recipe as item 11: real loan_id/policy_id keys from existing sheets + approved
  synthetic fields; deterministic IDs; MERGE-idempotent; an already-seeded graph needs a
  manual re-load to pick up new fields (auto-seed only fires on an empty graph).

---

## Summary table

| Area | Change | Files | Status |
|------|--------|-------|--------|
| Security utility | PII masking helpers (output-layer redaction) | `shared/utils/masking.py`, `tests/test_masking.py` | Done (inert until call-sites exist) |
| RAG / KB | Wire markdown loader into KB indexing | `services/rag_service/documents.py`, `tests/test_documents_loader.py` | Done |
| RAG / KB | Add BFSI knowledge-base content — 9 files: how_to_procedures, fees_and_charges, fraud_and_security, grievance_redressal, interest_rates, product_eligibility, regulatory_faqs, branch_atm_directory, bank_reference | `data/knowledge_base/*.md` (see log #3–#11 for per-file detail) | Done (9 of 9) |
| RAG / KB | KB verification eval set (pass/fail target) | `docs/phase2-kb-eval-set.md` | RUN 2026-06-28 — ALL PASS (pos 10/10, regr 2/2, neg 5/5) |
| Graph data | Fix Policy null-fields bug: new per-customer policy sheet + loader | `data/bfsi.xlsx` (new `Customer_Policy_data` sheet), `services/neo4j_service/loader.py`, `services/neo4j_service/writer.py` | Done — verified end-to-end (45 policies w/ coverage) |
| Graph data | Item 15: loan EMI schedule (summary props on :Loan) | `data/bfsi.xlsx` (new `Loan_Schedule_data` sheet), `loader.py`, `queries.py`, `writer.py` | Done — verified end-to-end (EMI in answer) |
| Graph data | Item 16: loan arrears / DPD (cols added to `Loan_Schedule_data`) | `data/bfsi.xlsx` (arrears cols), `loader.py`, `queries.py`, `writer.py` | Done — verified end-to-end (arrears in answer) |
| Infra fix | cx-data volume no longer shadows seed data; Neo4j re-seeds idempotently every startup | `docker-compose.yml`, `apps/api/main.py` | Done — verified from clean clone |
| Graph data | Item 12: premium payment history (cols on `Customer_Policy_data`) | `data/bfsi.xlsx` (premium-history cols), `loader.py`, `queries.py`, `writer.py` | Done — verified end-to-end (overdue premiums in answer) |
| RAG / KB | Items 13 & 14: network providers + claim filing guide | `data/knowledge_base/network_providers.md`, `data/knowledge_base/claim_filing_guide.md` | Done — verified (indexed + retrieved) |
| Graph data | Item 17: collateral & disbursement (new `Loan_Collateral_data` sheet) | `data/bfsi.xlsx`, `loader.py`, `queries.py`, `writer.py` | Done — verified end-to-end (collateral on secured only) |
| Tests | Updated 3 tests for Phase 2 behavior + fixed 1 pre-existing test-double | `tests/test_phase1.py` | 60/61 pass; 1 known pre-existing (see #21) |

---

## Detailed log

Each entry: **What / Why / Synthetic / Verified.** Synthetic = invented values (must be
listed). **Convention:** all KB/graph items marked "Done (code)" are unit/logic-verified
locally; full end-to-end (OpenSearch retrieval / Neo4j re-seed) is pending the Docker stack
unless an entry says otherwise — not repeated per entry.

### 1. PII masking utility — `shared/utils/masking.py`
- **What:** PII masking helpers (`mask_account/card/phone/email/pan/text`); pure, defensive.
- **Why:** core-banking data (Group C) must show masked values (last-4), not full numbers. No masking utility existed before. NOTE: must not mask loan/claim/policy IDs or amounts.
- **Synthetic:** none.
- **Verified:** `tests/test_masking.py` 10/10 pass. Inert — nothing imports it yet (zero behavior change).

### 2. Markdown KB loader fix — `services/rag_service/documents.py`
- **What:** `load_knowledge_documents()` now loads markdown **and** PDF.
- **Why:** `_load_markdown_kb()` existed but was never called; Phase 1 indexed PDF only. Modifies Phase 1 behavior (approved).
- **Synthetic:** none.
- **Verified:** `tests/test_documents_loader.py` 2/2 pass.

### 3. KB content — `data/knowledge_base/how_to_procedures.md`
- **What:** How-to Q&A: block/replace card, reset net-banking, lockout, add payee (cooling-off), update mobile/email, statements, account closure, security reminder.
- **Why:** High-volume how-to queries had no KB coverage → escalations.
- **Synthetic:** `1800-200-1947` (helpline), `1800-200-1948` (card-blocking) — only invented values. Bank/app/portal kept generic ("your bank", "mobile banking app", "net-banking portal"). Omitted: support email, SMS short-code.
- **Verified:** loads → 10 chunks, tagged `knowledge_base`, no PDF regression.

### 4. KB content — `data/knowledge_base/fees_and_charges.md`
- **What:** Fees Q&A: ATM, NEFT/RTGS/IMPS/UPI, min-balance, card fees/late-payment, cheque return, loan foreclosure/prepayment, statements/SMS alerts, disputing a charge.
- **Why:** Fee/charge queries are very high-volume and had no KB coverage → escalations.
- **Synthetic:** all rupee amounts (ATM ₹20/₹21, IMPS ₹5/₹15, min-balance ₹150–600, card annual ₹150–750, late fee ₹500–1,300, cheque return ₹300–500, foreclosure 2–4%, statement ₹50–100, SMS ₹15–25/qtr) + helpline `1800-200-1947`. Real RBI norms (free-ATM minimums, no floating-retail foreclosure penalty, GST, UPI free) stated as fact.
- **Verified:** loads → 7 chunks, tagged `knowledge_base`, no regression.

### 5. KB content — `data/knowledge_base/fraud_and_security.md`
- **What:** Fraud/security Q&A: report unauthorised txn + block card, what happens after reporting, bank never asks PIN/OTP/CVV, common scams (phishing/vishing/fake-KYC/UPI-collect/fake-reward), spotting genuine messages, safe-banking habits, card dispute/chargeback.
- **Why:** Supports `fraud_report` / `complaint` paths — gives useful guidance while a human is assigned.
- **Synthetic:** `1800-200-1948` (fraud/card-blocking), `1800-200-1947` (helpline) — only invented values. RBI limited-liability stated as a PRINCIPLE only (no invented day/amount tiers — deliberate, to avoid misinforming on liability). Generic bank/app/portal. Omitted: support email, SMS short-code.
- **Verified:** loads → 7 chunks, tagged `knowledge_base`, no regression.

### 6. KB content — `data/knowledge_base/grievance_redressal.md`
- **What:** Grievance Q&A: raise/track a complaint (L1), escalate to bank GRO/Nodal Officer (L2), escalate to RBI Ombudsman RB-IOS / IRDAI Bima Bharosa / SEBI SCORES (L3), info to retain.
- **Why:** Supports the `complaint` intent with the real India escalation ladder.
- **Synthetic:** `1800-200-1947` (helpline) and complaint-ref format `GRV-xxxxxxxx` — only invented values. Real regulator facts stated as fact (RB-IOS exists & free, IRDAI/Bima Bharosa, SEBI SCORES, ~30-day bank resolution window before Ombudsman). Role titles generic (GRO/Nodal Officer), no named individuals/addresses. Omitted: support email, SMS short-code.
- **Verified:** loads → 6 chunks, tagged `knowledge_base`, no regression.

### 7. KB content — `data/knowledge_base/interest_rates.md`
- **What:** Rates Q&A: savings, FD/RD (incl. senior-citizen uplift), loans (home/car/personal/education/business/gold), credit-card finance charge, why floating/deposit rates change.
- **Why:** Common rate enquiries had no KB coverage.
- **Synthetic:** all rates as RANGES (savings 2.75–3.5%, FD 3.0–7.25%, senior +0.50%, RD 5.5–7.0%, home ~8.5%+, car 9–11%, edu 9–13%, personal 11–18%, business 12–18%, gold 9–15%, card ~3.0–3.75%/mo) + helpline `1800-200-1947`. Framed "indicative / check current". Real norms (EBLR/repo-linked, tenure-based FD, senior uplift, booked rate fixed) stated as fact.
- **Verified:** loads → 5 chunks, tagged `knowledge_base`, no regression.

### 8. KB content — `data/knowledge_base/product_eligibility.md`
- **What:** Products & eligibility Q&A: loans (personal/home/car/education/business/gold), insurance (term/health/auto/home/travel/ULIP/endowment/whole-life/retirement), deposits (FD/RD), how to apply.
- **Why:** Product/eligibility queries had no customer-facing KB; now consistent with the graph catalogue.
- **Synthetic:** ONLY `1800-200-1947` (helpline). All product names + eligibility criteria are taken DIRECTLY from the real `Loan_Policy_Product_data` sheet in `bfsi.xlsx` (not invented) — keeps KB aligned 1:1 with the Neo4j `Product` nodes. No invented amounts/rates added here (rates live in interest_rates.md). Generic bank/app/portal. Omitted: support email, SMS short-code.
- **Verified:** loads → 6 chunks, tagged `knowledge_base`, no regression.

### 9. KB content — `data/knowledge_base/regulatory_faqs.md`
- **What:** Regulatory Q&A: DICGC deposit insurance, nomination, insurance free-look, KYC/re-KYC, inactive/dormant accounts + DEA Fund, customer rights/data privacy.
- **Why:** Common regulatory/rights questions had no KB coverage.
- **Synthetic:** ONLY `1800-200-1947` (helpline). All regulatory facts are REAL published figures stated as fact (DICGC ₹5 lakh/depositor/bank, 10-yr unclaimed→DEA Fund, ~2-yr dormancy, free-look ~15–30 days, periodic re-KYC). Data-privacy stated generally (not claiming built compliance). Generic bank/app/portal. Omitted: support email, SMS short-code.
- **Verified:** loads → 6 chunks, tagged `knowledge_base`, no regression.

### 10. KB content — `data/knowledge_base/branch_atm_directory.md`
- **What:** Branch/ATM Q&A: how to use the locator, typical branch hours, sample branches, IFSC explanation, branch-vs-ATM services.
- **Why:** "find a branch/ATM/IFSC" queries had no KB coverage.
- **Synthetic:** ~5 sample branches with FAKE `BANK0…` IFSCs (Mumbai/Delhi/Bangalore/Chennai/Hyderabad — cities that exist in real Customer_data), `1800-200-1947` (helpline). Framed as examples + "use the locator" (system has no real branch network). Standard facts stated as fact (typical branch hours, IFSC 11-char format, ATM 24/7). Generic bank/app/portal. Omitted: support email, SMS short-code.
- **Verified:** loads → 5 chunks, tagged `knowledge_base`, no regression.

### 11. KB content — `data/knowledge_base/bank_reference.md`
- **What:** Reference Q&A: IFSC format, MICR format, IFSC-vs-MICR usage, card-network-by-first-digit, where to find your codes.
- **Why:** Code/identifier queries had no KB coverage.
- **Synthetic:** sample IFSC `BANK0001234`, sample MICR `400123456`, illustrative BIN first-digit map (4=Visa, 5=MC, 6=RuPay/Discover, 3=Amex), `1800-200-1947` (helpline) — all clearly illustrative. Real standards stated as fact (IFSC 11-char structure, MICR 9-digit, MII first-digit network rule). No full/real issuer BINs invented. Generic bank/app/portal. Omitted: support email, SMS short-code.
- **Verified:** loads → 5 chunks; ALL 9 markdown KB files index (66 chunks total), no regression.

### 12. KB verification eval set — `docs/phase2-kb-eval-set.md`
- **What:** Defined the pass/fail target for end-to-end KB verification: 10 positive cases (KB should answer, should NOT escalate) + 2 regression cases (old PDF must still retrieve) + 5 negative cases (must STILL escalate/refuse). Hard gate per question = R (retrieval) + E (escalation); A (answer wording) is a soft/quality signal. Overall bar: ≥8/10 positive, both regression cases retrieve a PDF chunk, and all negative cases still escalate.
- **Why:** Judge verification against a fixed bar set before running, not rationalised after. Positive cases target content unique to the new files (avoid overlap with the original PDF's topics). Negative cases guard the inverse risk — that richer KB makes the bot over-confident and stops escalating fraud/dispute/balance/human/complaint.
- **Synthetic:** none (it's a test spec).
- **Verified:** N/A — this is the spec; execution needs the Docker stack (OpenSearch + Groq). Note: local env can't run embeddings (torch DLL crash `0xc0000139`), so verification must run inside Docker.

### 13. Graph data — Policy null-fields fix (`Customer_Policy_data` + loader/writer)
- **What:** New `Customer_Policy_data` sheet (45 rows, per-customer policies); rewrote `_load_policies()` to set the fields `get_policy_status()` queries (coverage_inr, premium_inr, maturity_date, next_premium_due, +policy_number/frequency/paid_to/status); writer seed updated. Links Policy→Product (by type), preserves Policy→Claim.
- **Why:** BUG FIX — query asked for coverage/premium/maturity but the old loader set only 3 fields → always null. New sheet = per-customer policies, distinct from the `Loan_Policy_Product_data` catalogue.
- **Synthetic:** CustomerID + PolicyType reused-real (Claim_data, 22 customers). Synthetic: coverage ₹3L–1cr by type, premium ₹1.5k–60k by type, PolicyNumber `PN-2023-NNNNNN`, frequency/paid-to/next-due dates, maturity (long-dated for Life/Term/ULIP; blank for annual-renewal types), status (mostly Active). PolicyID `POL<digits><typecode>`.
- **Verified:** 45 rows, CustomerIDs valid, PolicyIDs unique, no empty coverage/premium; existing 4 sheets untouched; loader+writer compile. NOTE: Neo4j auto-seed fires only on an EMPTY graph — already-seeded graphs need a manual re-load (applies to all graph entries).

### 14. Graph data — Item 15: loan EMI schedule (`Loan_Schedule_data` + loader/query/writer)
- **What:** New `Loan_Schedule_data` sheet → `_load_loan_schedules()` sets summary EMI props on existing `:Loan` nodes (emi_amount_inr, outstanding_principal_inr, next_emi_date, foreclosure_amount_inr, tenure_months, emis_paid). Extended `get_loan_status()` to return them and the `neo4j_answer()` loan branch to append "EMI … due …, Outstanding …, Foreclosure …" — ONLY for disbursed loans that have a schedule. Writer seed: the Approved demo loan now carries the same EMI props.
- **Why:** "what's my next EMI / outstanding / foreclosure" is the highest-volume loan query; previously unanswerable.
- **Synthetic:** LoanID/CustomerID reused-real. TenureMonths synthetic by type (Home 240, Car 60, Personal 36, Edu 84, Business 60, Gold 12), EMIs_Paid synthetic. EMI_Amount / Outstanding / Foreclosure are DERIVED from the real LoanAmount + InterestRate via the standard EMI formula (consistent, not random — verified LN001 = ₹16,727 matches independent calc). Only disbursed (Approved) loans appear in the sheet; non-disbursed loans have no row (= no schedule). Non-numeric rate (LN004 'N/A', Rejected) safely excluded.
- **Verified:** EMI math cross-checked; existing sheets preserved; loader/queries/writer compile; answer-formatting logic-tested (EMI shown for disbursed only).
- **Refinement (later):** sheet originally had 37 rows (one per loan, 31 with null EMI fields + a `HasSchedule` flag). Reduced to 6 disbursed-loan rows and dropped the `HasSchedule` column — arrears (item 16) also apply only to disbursed loans, so the 31 null rows carried no real information. Loader simplified to match; absent rows handled by existing guards. See entry #16.

### 15. Graph data — Item 16: loan arrears / DPD (arrears cols on `Loan_Schedule_data`)
- **What:** Added 5 arrears columns to the existing `Loan_Schedule_data` sheet (no new sheet): DPD, Overdue_Amount_INR, Penalty_INR, Bucket, Collections_Stage. `_load_loan_schedules()` now also writes dpd/overdue/penalty/arrears_bucket/collections_stage onto EVERY `:Loan` (current loans = DPD 0). `get_loan_status()` returns them; `neo4j_answer()` appends an "Overdue: … (N days past due, late fee …)" clause per overdue loan, and for `loan_default_notice` leads with a factual fair-practice summary ("clear the overdue amount to avoid charges / credit impact" — no threatening language) or "no overdue amount on record".
- **Why:** Gives `loan_default_notice` real figures for the holding answer. (Intent still escalates — it's in MANUAL_REVIEW_INTENTS; item 16 only enriches the holding message, doesn't change escalation.)
- **Synthetic:** LoanID/CustomerID reused-real. Only disbursed loans can be in arrears; 2 put into arrears (LN005 35 DPD/1 EMI overdue; LN009 65 DPD/2 EMIs), rest current (DPD 0). Overdue_Amount DERIVED from the row's EMI (LN005=1×EMI, LN009=2×EMI — verified). Penalty ₹750/missed EMI (synthetic). Buckets/stages standard (Current/1-30/31-60/61-90/90+).
- **Verified:** overdue=EMI×missed cross-checked; loader/queries/writer compile; answer logic-tested (overdue summary + fair-practice tone; "no overdue" path).

### 16. Refinement — shrink `Loan_Schedule_data` to disbursed loans only
- **What:** Rebuilt `Loan_Schedule_data` from 37 rows → 6 (disbursed loans only) and dropped the now-redundant `HasSchedule` column (every remaining row has a schedule). Simplified `_load_loan_schedules()` accordingly (no HasSchedule check; sets EMI + arrears props in one write per row).
- **Why:** The 31 non-disbursed rows held only null EMI fields + filler DPD=0. A non-disbursed loan has no EMI obligation, so it can have neither a schedule nor arrears — its absence from the sheet says exactly that. (Corrects an earlier over-modeling: the claim that "arrears apply to all loans, so I need a row per loan" was wrong.)
- **Synthetic:** unchanged — same 6 loans, same values (incl. LN005/LN009 arrears).
- **Verified:** loader reads 6 rows, HasSchedule gone, all rows have EMI, arrears preserved; existing sheets intact; loader compiles.

### 17. Infra fix — stale-data robustness (`docker-compose.yml`, `apps/api/main.py`)
- **What:** (1) `cx-data` volume now mounts at `/app/data/db` (not `/app/data`) + `DATABASE_PATH=/app/data/db/cx_phase1.db` + `mkdir -p` in command — so seed data (`bfsi.xlsx`, `knowledge_base/`) is served fresh from the image, never shadowed by the volume; only the runtime SQLite DB persists. (2) Removed the `_seed_neo4j` "skip if data exists" guard — `load_bfsi_data()` (MERGE-based, idempotent) now runs every startup, so data-model changes always load.
- **Why:** TWO bugs found during verification, same class (stale persisted state blocked new data): the volume shadowed the updated workbook (container had the old 4-sheet xlsx + old KB), and the seed-guard froze the graph at first seed (new sheets never loaded). Both would bite any teammate/branch with an existing volume — not just us.
- **Synthetic:** none (infra).
- **Verified:** from FULLY CLEAN volumes (simulated fresh clone) + rebuild, startup seed ALONE produced 45 policies w/ coverage, 6 loans w/ EMI, 2 in arrears — and `neo4j_answer` returns real policy/EMI/arrears text. No manual steps.

### 18. Graph data — Item 12: premium payment history (cols on `Customer_Policy_data`)
- **What:** Added 6 premium-history columns to `Customer_Policy_data` (Premiums_Paid, Last_Premium_Date, Premium_Status, Overdue_Premium_INR, Late_Fee_INR, Grace_Period_Days). `_load_policies` sets them as props on `:Policy`; `get_policy_status` returns them; `policy_status` answer appends a factual "Premium overdue: ₹X, late fee …, grace N days — please pay to keep active" clause for overdue policies only. Writer seed updated (demo policies Paid).
- **Why:** Completes the policy side started in item 11 — surfaces premium-payment state in policy_status answers.
- **Synthetic:** Premium_Status DERIVED from item 11 status (Active→Paid; Due→Overdue 1×premium; Lapsed→Overdue 2×premium) — consistent. Overdue_Premium DERIVED from premium_inr. Late fee ₹250/missed; grace 30d annual/15d monthly (real IRDAI-style norm); Premiums_Paid synthetic. 7 overdue (matches 4 Lapsed + 3 Due).
- **Verified:** end-to-end — 45 policies w/ premium_status (7 overdue); `policy_status` answer for CUST105 shows overdue clause on Due/Lapsed policies only, Active policy clean.

### 19. KB content — Items 13 & 14: `network_providers.md` + `claim_filing_guide.md`
- **What:** Two reference KB files. network_providers: cashless vs reimbursement, locator, pre-auth, TPA, sample providers. claim_filing_guide: documents per claim type (health/motor/life/travel) + settlement timelines.
- **Why:** Items 13/14 are FAQ-shaped reference data → KB, not graph. Network/claim-doc queries had no coverage.
- **Synthetic:** sample hospitals (City Care/Mumbai, Metro Health/Delhi, Sunrise/Bangalore, Lakeside/Chennai) + garages (AutoFix/Pune, DriveCare/Hyderabad); helpline `1800-200-1947`; indicative operational TATs (health reimb ~15–30d, motor ~7–15d). Real IRDAI norm stated as fact (life claim 30-day settlement). Doc checklists standard. Generic insurer/app.
- **Verified:** 77 docs indexed (0 errors); both files retrieve for their queries (network/TPA → network_providers.md; death-claim docs → claim_filing_guide.md).

### 20. Graph data — Item 17: collateral & disbursement (new `Loan_Collateral_data` sheet)
- **What:** New `Loan_Collateral_data` sheet (37 rows) → `_load_loan_collateral()` sets collateral_type/value/ltv (secured loans only) + sanctioned/disbursed (all loans) on `:Loan`. `get_loan_status` returns them; loan answer appends "Collateral: <type> (₹X, LTV Y%)" for secured + "Disbursed: ₹A of ₹B sanctioned". Writer seed updated (Personal=unsecured, Home=secured).
- **Why:** "what collateral / how much disbursed / sanctioned" loan queries had no data.
- **Synthetic:** LoanID/CustomerID + Sanctioned (=real LoanAmount) reused-real. Secured types = Home(Property,75% LTV)/Car(Vehicle,85%)/Business(Property-Equipment,60%); Personal+Education = unsecured, NO collateral. Collateral_Value DERIVED from amount/LTV (always exceeds loan). Disbursed = full for Approved, else 0.
- **Verified:** end-to-end — 37 loans w/ sanction, 20 secured w/ collateral; loan_status for CUST101 shows collateral on Home (secured, ₹0 disbursed/Under Review) and none on Personal (unsecured, fully disbursed).

### 21. Tests — full suite run + fixes (`tests/test_phase1.py`)
- **What:** Ran full pytest in-container after all Phase 2 changes → 60/61 pass. Fixed: (a) `Recorder.send_text` mock now accepts `**kwargs` (was missing `reply_to_message_id` — a PRE-EXISTING failure unrelated to our work, was breaking 3 tests); (b) `kb_documents_are_knowledge_base_type` now allows `.md` as well as `.pdf` (our markdown KB change); (c) `rag_discards_non_kb_contexts` now asserts the non-KB doc is dropped + KB doc kept (tolerates extra real KB contexts the keyword fallback adds).
- **Why:** Confirm no regressions; align tests with approved Phase 2 behavior.
- **Synthetic:** none.
- **Verified:** 60 passed. KNOWN PRE-EXISTING (1): `test_five_question_kb_and_graph_e2e_matrix` expects `neo4j_graph` backend but the mock-based full-orchestration run returns `keyword_fallback`. This test was already red at session start (masked by the reply_to_message_id error). The real app is verified working — live stack returns neo4j_graph answers (policy/EMI/arrears/collateral all confirmed). Root cause is in the test's Neo4j mock vs. orchestration, NOT the production data work. Left as-is.
