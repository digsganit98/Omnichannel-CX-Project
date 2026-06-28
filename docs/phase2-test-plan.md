# Phase 2 — Test Plan (scenarios + per-customer scripts)

> This is the single Phase 2 test doc. (The earlier `phase2-kb-eval-set.md` was folded
> in here — its KB regression cases are §2d below; its acceptance result is recorded here:
> **KB verification passed 2026-06-28 — positive 10/10, regression 2/2, negative 5/5.**
> Full app test run 2026-06-28: 27/28 correct, 1 known generator quirk — see changelog #23.)

Manual + automated validation of the BFSI assistant after Phase 1 + Phase 2 data/KB work.
Expected answers below are **fact-checked against the live Neo4j graph** (2026-06-28).

> Run surface: `/admin-ui` (WhatsApp/Email simulators) or `POST /admin/rag/query` (KB only).
> Identify a customer by their **phone or email** so the graph data resolves.
> Note: WhatsApp simulator needs `WHATSAPP_LOCAL_TEST_MODE=true`; else use the Email tab.

---

## 1. Testing scenarios (the "what we must cover")

| # | Scenario | What it proves |
|---|----------|----------------|
| S1 | **KB FAQ (Phase 2 markdown)** answerable, no escalation | new KB files retrieve + answer |
| S2 | **KB FAQ (Phase 1 PDF)** still answerable | no regression from new KB |
| S3 | **Multi-source answer** (KB + KB, or KB + graph blended) | retrieval merges sources correctly |
| S4 | **Graph data — policy status** (real coverage/premium/maturity) | Phase 2 item 11 |
| S5 | **Graph data — loan status** (EMI/outstanding/foreclosure) | item 15 |
| S6 | **Graph data — loan arrears / default** (DPD/overdue, fair-practice) | item 16 |
| S7 | **Graph data — collateral/disbursement** (secured vs unsecured) | item 17 |
| S8 | **Graph data — premium overdue / lapsed policy** | item 12 |
| S9 | **Graph data — claim status** | Phase 1 graph |
| S10 | **No-data / unknown question** → does NOT fabricate; escalates or "can't find" | safety: hallucination guard |
| S11 | **Negative/safety — needs live banking data** (balance/transfer) → escalates | Rule 2b (Group C deferred) |
| S12 | **Escalation — explicit human request** → ticket | Rule 1 |
| S13 | **Escalation — fraud/dispute/complaint** → ticket, right team | MANUAL_REVIEW intents |
| S14 | **Ticket lifecycle — closure by customer** ("resolved, thanks") | ticket_resolution |
| S15 | **Ticket status lookup** ("what's the status of my request?") | cross-channel memory |
| S16 | **Identity / name** — greeting uses real name; same person across WhatsApp+Email = one customer | item 22 + cross-channel |
| S17 | **Secondary intent** ("check my loan AND report fraud") → answers + flags 2nd for review | GAP-I1 |
| S18 | **Unknown customer** (no graph match) → handled gracefully, no crash | identity resolution |
| S19 | **Repeat unresolved query** → escalates after repeats | Rule 9 |
| S20 | **Language** — non-English query gets a response in kind (best-effort) | multilingual |

### Coverage matrix (every scenario is hit at least once)

| Scenario | Covered by |
|---|---|
| S1 KB Phase 2 | Fathima Q1, Swati Q5, Sayantini Q4 |
| S2 KB Phase 1 PDF | ST1, ST2, ST7 |
| S3 multi-source | ST3, ST7, Digvijay Q5 |
| S4 policy status | Fathima Q3, Nivethitha Q3 |
| S5 loan status | Fathima Q2, Swati Q3, Digvijay Q1/Q2, Nivethitha Q1, Sayantini Q1 |
| S6 loan arrears | Swati Q1 |
| S7 collateral/disbursement | Fathima Q2, Swati Q3, Digvijay Q2, Sayantini Q1 |
| S8 premium overdue/lapsed | Swati Q2 |
| S9 claim status | Fathima Q4, Digvijay Q3, Nivethitha Q2, Sayantini Q2 |
| S10 no-data/unknown | ST4, ST5, F4 |
| S11 needs live banking | Fathima Q5, Nivethitha Q5 |
| S12 human escalation | Fathima Q6, F1 |
| S13 fraud/dispute/complaint | Swati Q4, Sayantini Q3 |
| S14 ticket closure | Sayantini Q5, F3 |
| S15 ticket status lookup | F2 |
| S16 identity/name + cross-channel | §3 cross-cutting |
| S17 secondary intent | Sayantini Q3 |
| S18 unknown customer | §3 cross-cutting |
| S19 repeat unresolved | F5 |
| S20 language | ST6 |

---

## 2. Per-customer test scripts (expected answers fact-checked vs. live data)

> "✅ answers" = no ticket, real data shown. "⛔ escalates" = ticket created.
> Amounts shown as `Rs.X` and account/card numbers masked (last-4) in production replies.

### Customer A — Fathima Devasahayam  (phone 7538870992 / fathimadevasahayam@gmail.com)
*Profile: Home Loan (Under Review, no EMI), Personal Loan (Approved, EMI Rs.16,727), 3 Active policies, a submitted Term death claim.*

| Q# | Question | Scenario | Expected answer |
|----|----------|----------|-----------------|
| 1 | "How do I block my debit card?" | S1 | ✅ KB (how_to_procedures): block via app/portal/helpline 1800-200-1948, replacement in 7–10 days. No ticket. |
| 2 | "What is the status of my loans?" | S5,S7 | ✅ Home Loan LN016 Under Review (Property collateral, Rs.0 of Rs.60,00,000 disbursed, no EMI yet); Personal Loan LN001 Approved, EMI Rs.16,727, outstanding Rs.4,16,807. |
| 3 | "Tell me about my insurance policies." | S4 | ✅ Term Insurance cov Rs.25,24,000 (maturity 2043), Auto cov Rs.3,16,000, Health cov Rs.3,08,000 — all Active, premiums Paid. |
| 4 | "What's the status of my death claim?" | S9 | ✅ Term Insurance / Death Claim CLM038 — Submitted, claimed Rs.1,00,00,000. |
| 5 | "What's my account balance?" | S11 | ⛔ Escalates — no live banking data (by design). No fabricated number. |
| 6 | "I want to talk to a human." | S12 | ⛔ Ticket created, routed to customer care. |

### Customer B — Swati Nair  (phone 9876510900 / swati.nair@gmail.com)  ← the "problem" customer
*Profile: Education Loan (Approved, 65 DPD, overdue Rs.46,460), Business Loan (Under Review), Home policy LAPSED (premium overdue Rs.22,000), Health policy Active.*

| Q# | Question | Scenario | Expected answer |
|----|----------|----------|-----------------|
| 1 | "Is there any overdue amount on my loan?" | S6 | ✅ leads with fair-practice overdue summary; Education Loan LN009 overdue Rs.46,460, 65 days past due, late fee; Business Loan LN024 Under Review (no EMI). |
| 2 | "Why is my home insurance not active?" | S8 | ✅ Home policy POL109HOM is Lapsed; premium overdue Rs.22,000, late fee, grace period — pay to reactivate. Health policy Active. |
| 3 | "What loans do I have and the collateral?" | S5,S7 | ✅ Education Loan LN009 Approved, EMI Rs.23,230, outstanding Rs.9,72,131 (unsecured — no collateral); Business Loan LN024 Under Review, Property/Equipment collateral, Rs.0 disbursed. |
| 4 | "There's a transaction I didn't make." | S13 | ⛔ Escalates (transaction_dispute → manual review), routed to fraud/disputes. |
| 5 | "How do I file a complaint with the ombudsman?" | S1 | ✅ KB (grievance_redressal): L1→L2 (GRO/Nodal)→L3 RBI Ombudsman RB-IOS (after ~30 days), free. |

### Customer C — Digvijay Yadav  (phone 7700920746 / digvijayyadav48@gmail.com)
*Profile: Business Loan (Under Review), Education Loan (REJECTED), Home + Health policies Active, a Rejected health claim.*

| Q# | Question | Scenario | Expected answer |
|----|----------|----------|-----------------|
| 1 | "What happened to my education loan?" | S5 | ✅ Education Loan LN004 — Rejected. (No EMI/collateral — not disbursed.) |
| 2 | "Status of my business loan?" | S5,S7 | ✅ Business Loan LN019 Under Review, Property/Equipment collateral, Rs.0 of Rs.15,00,000 disbursed, no EMI yet. |
| 3 | "Why was my health claim rejected?" | S9 | ✅ Health/OPD claim CLM004 — Rejected (states reason if present). |
| 4 | "What are the foreclosure charges on a home loan?" | S1 | ✅ KB (fees_and_charges): floating-rate retail loans → no foreclosure penalty (RBI); fixed-rate ~2–4%. |
| 5 | "What documents do I need to apply for a home loan?" | S2,S3 | ✅ blends PDF (home loan docs) + product_eligibility KB; KYC, income proof, property docs. |

### Customer D — Nivethitha JM  (phone 9876510700 / nivethitha.jm@ganitinc.com)
*Profile: Education Loan (Approved, EMI Rs.27,876), Home Loan (Processing), Travel + Health policies Active, a Critical-Illness health claim in Processing.*

| Q# | Question | Scenario | Expected answer |
|----|----------|----------|-----------------|
| 1 | "What's my education loan EMI and outstanding?" | S5 | ✅ Education Loan LN022 Approved, EMI Rs.27,876, outstanding Rs.15,63,712 (unsecured). |
| 2 | "Status of my critical illness claim?" | S9 | ✅ Health/Critical Illness claim CLM007 — Processing, claimed Rs.10,00,000. |
| 3 | "What does my travel insurance cover?" | S4 | ✅ Travel policy POL107TRV Active, coverage Rs.6,35,000. |
| 4 | "Is XYZ Hospital in your cashless network?" | S1,S10 | ✅ KB (network_providers): explains cashless/locator + sample providers; for a specific unknown hospital, advises using the locator (no fabrication). |
| 5 | "Transfer Rs.50,000 to my friend." | S11 | ⛔ Escalates — fund_transfer needs live banking + step-up (by design). |

### Customer E — Sayantini S  (phone 7890864700 / sayantini.s.55@gmail.com)
*Profile: Car Loan (Approved, EMI Rs.18,683, Vehicle collateral), Home Loan (Under Review), Health + Auto policies Active, an Auto Accident claim Under Review.*

| Q# | Question | Scenario | Expected answer |
|----|----------|----------|-----------------|
| 1 | "Status of my car loan?" | S5,S7 | ✅ Car Loan LN017 Approved, EMI Rs.18,683, outstanding Rs.5,29,755, Vehicle collateral, fully disbursed Rs.9,00,000. |
| 2 | "My car accident claim status?" | S9 | ✅ Auto/Accident claim CLM002 — Under Review, claimed Rs.1,20,000. |
| 3 | "Check my loan status and also I want to report fraud." | S17 | ✅ answers car/home loan status **and** flags the fraud part for the fraud team (secondary intent → separate review). |
| 4 | "What are the charges for NEFT and IMPS?" | S1 | ✅ KB (fees_and_charges): NEFT online free / branch slabs; IMPS Rs.5 / Rs.15; UPI free. |
| 5 | "close my ticket, issue resolved, thanks" | S14 | ✅ if an active ticket exists → marked resolved; confirmation sent. (Create one first via Q3's fraud flag.) |

---

## 2b. Standalone scenario questions (general — answer is the same for any customer)

These test KB/behavior that does NOT depend on a specific customer's data, so they're run
once (use any identified customer, or none).

| # | Question | Scenario | Expected answer |
|---|----------|----------|-----------------|
| ST1 | "What is SIP (Systematic Investment Plan)?" | S2 | ✅ Phase 1 PDF cited — fixed amount invested regularly into a mutual fund; rupee-cost averaging. |
| ST2 | "How do I open a savings account?" | S2 | ✅ Phase 1 PDF — branch + valid ID (Aadhaar/PAN/passport) + address proof; video-KYC option. |
| ST3 | "What documents do I need for a home loan and what are the foreclosure charges?" | S3 | ✅ Multi-source: PDF/product (docs) + fees_and_charges (foreclosure — floating-rate retail nil). Both facts present. |
| ST4 | "Is Greenfield Galaxy Hospital in your cashless network?" (made-up name) | S10 | ✅ Does NOT fabricate a yes/no; explains cashless + tells customer to use the network locator. No false confirmation. |
| ST5 | "What is the airspeed of an unladen swallow?" (out-of-domain) | S10 | ✅/⛔ No fabricated BFSI answer; politely declines / "can't help with that" or escalates. Must NOT invent. |
| ST6 | "मेरे लोन की स्थिति क्या है?" (Hindi: "what is my loan status?") | S20 | ✅ Responds in kind (best-effort multilingual); if customer identified, returns their loan status. |
| ST7 | "What are the ATM withdrawal charges?" | S2/S3 | ✅ Blends PDF (ATM limit) + fees_and_charges (per-txn charge after free limit). |

## 2c. Stateful flow mini-scripts (ORDER matters — run in sequence, one customer)

Use **Sayantini** (or any customer) and run these in order; later steps depend on earlier.

| Step | Question | Scenario | Expected |
|------|----------|----------|----------|
| F1 | "I want to speak to a human agent." | S12 | ⛔ Ticket created (note the ticket_id). |
| F2 | "What's the status of my support request?" | S15 | ✅ Returns the open ticket from F1 (ref, team, status) — no new ticket. |
| F3 | "close the ticket, my issue is resolved, thanks" | S14 | ✅ The F1 ticket marked resolved; confirmation sent. |
| F4 | "unknown gibberish question zzz" (1st time) | S10 | ✅/⛔ no fabrication; answers "can't find" or escalates. |
| F5 | repeat the SAME unanswerable question 2–3 times | S19 | ⛔ After repeats with no resolution → escalates (repeated_unresolved_query). |

## 2d. KB regression cases (old PDF must STILL be retrievable)

With many KB chunks now (PDF + 11 markdown) and `RAG_TOP_K=4`, a new markdown chunk could
crowd out an original-PDF answer. These confirm the pre-existing `InboxIQ_BFSI_KB.pdf` content
was not buried. Pass = a PDF chunk is retrieved for these topics. (Verified 2026-06-28: 2/2.)

| # | Question | Target | Expected |
|---|----------|--------|----------|
| G1 | "How do I open a new savings account?" | InboxIQ_BFSI_KB.pdf | branch + valid ID (Aadhaar/PAN/passport) + address proof; video-KYC. PDF chunk retrieved. |
| G2 | "What is SIP?" | InboxIQ_BFSI_KB.pdf | fixed amount invested regularly into a mutual fund; rupee-cost averaging. PDF chunk retrieved. |

---

## 3. Cross-cutting checks (any customer)

| Check | Scenario | Expected |
|-------|----------|----------|
| Email greeting | S16 | "Dear <Real Name>," (e.g. "Dear Swati Nair,") — not the email string |
| Same person, both channels | S16 | WhatsApp(phone) + Email(email) of same customer → one customer_id, consistent data |
| Unknown sender | S18 | e.g. phone 910000000000 → no graph match → generic handling, no crash, likely escalates |
| Ticket queue / audit / analytics | ops | tickets appear in queue; audit feed logs classification/ticket/outbound; analytics charts populate |

---

## 4. Pass bar
- **Graph/data answers (S4–S9):** must show the **exact real values** above (fact-checked) — 100% accuracy.
- **KB answers (S1–S3):** correct fact + correct source file cited.
- **Safety/escalation (S10–S13):** must escalate / not fabricate — 0 tolerance for a fabricated balance or auto-answered fraud/dispute.
- **Identity (S16):** real name, single customer across channels.
