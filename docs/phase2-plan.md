# Phase 2 Plan — Omnichannel CX Accelerator for BFSI

> **Audience:** internal manager / steering review.
> **Goal:** turn the Phase 1 demo into a **sellable, BFSI-grade Product-as-a-Service** that a
> bank/NBFC/insurer can run in production and pass security, compliance & procurement gates.
> **Baseline:** [`phase1-overview.md`](phase1-overview.md). "Today" = Phase 1 as it exists in code.

## 0. TL;DR
Phase 1 is a strong **functional** demo (WhatsApp+Email, 16-intent taxonomy, 4-agent LangGraph,
Neo4j customer-360, cited RAG, ticketing+CRM sync, multilingual, analytics). **Phase 2 turns it into
a product a BFSI client will actually buy**, built on two pillars:

- **Pillar 1 — Features that win BFSI clients** *(§2, the priority):* verify-before-disclose, smart
  unknown-caller handling, **voice**, proactive alerts, cross-sell, agent console, self-service — plus
  multi-tenancy + configurability that make it a real **Product-as-a-Service** (sell to bank A *and* B).
- **Pillar 2 — Compliance-readiness** *(§9, the essential support):* the accelerator ships compliance
  **seams** (encryption, consent/DPDP, immutable audit, data-residency) the bank plugs *their* controls
  into — plus a **Compliance Matrix** that shortens their security review. We sell "compliance-ready,"
  not "we host your compliance."

Phase 2 = **14 workstreams** (W1–W14). §1 = gap analysis; §2 = the feature pillar; §3–8 = workstream
detail; §9 = the compliance pillar; §10 = roadmap; §12 = feature-scoring matrix; §15 = role review.

## 1. Gap analysis (Phase 1 vs. "sellable to BFSI")

| # | Area | Today | Gap / risk | Severity |
|---|------|-------|-----------|----------|
| G1 | **Caller auth** | `resolve_customer()` auto-creates for any sender | No step-up before exposing financial data; spoofed number → data leak | **Critical** |
| G2 | **Unregistered contacts** | Unknown number/email silently becomes a customer | No engage→identify (ask-back) flow; no lead-capture / fraud-flag fallback | **Critical** |
| G3 | **Tenant isolation** | Single shared SQLite/Neo4j/OpenSearch | Can't onboard 2 banks; no per-client boundary/keys/KB/branding | **Critical** |
| G4 | **Data protection** | Plaintext PII; secrets in `.env`; PII in logs | No encryption-at-rest, masking, secrets manager, DPDP consent/retention/erasure | **Critical** |
| G5 | **Audit/non-repudiation** | App-writable `audit_events` | Not immutable/tamper-evident; RBI expects WORM + retention | High |
| G6 | **Channels** | WhatsApp + Email | No **voice**, web chat / in-app SDK, IVR deflection, social | High |
| G7 | **System of record** | SQLite in a volume | No HA, concurrent writers, backup/PITR/DR | High |
| G8 | **Scale/async** | Synchronous pipeline (LLM inline) | No queue/backpressure/spike handling; in-process retry only | High |
| G9 | **AI safety/governance** | System-prompt guardrails + rules | No PII redaction, prompt-injection/jailbreak defense, financial-advice guard, model-output logging (SR 11-7/RBI) | High |
| G10 | **Human-in-the-loop** | Tickets only | No agent console, AI-assist, warm handoff, supervisor barge-in | High |
| G11 | **Validation depth** | Identity = channel ownership | No KYC-tier-aware exposure, OTP/KBA/biometric step-up, risk-based auth | High |
| G12 | **Observability/SLO** | Logs + workflow trace | No metrics/traces/dashboards, alerting, SLO budgets, cost-per-conversation | Medium |
| G13 | **Configurability** | Intents/teams/SLA/prompts hard-coded | Every client needs code changes; no admin config | Medium |
| G14 | **Knowledge governance** | Markdown, manually indexed | No approval/versioning/freshness/source-enforcement UI | Medium |
| G15 | **Outbound/notifications** | Same-channel reply only | No proactive alerts (EMI/fraud/KYC), throttling, WhatsApp HSM template/consent mgmt | Medium |
| G16 | **Testing/quality** | Few pytest tests, no CI | No eval harness, prompt regression, red-team, load tests | Medium |
| G17 | **Accessibility/fairness** | Multilingual replies | No WCAG, no bias testing (DPDP/RBI fair-treatment) | Low |

## 2. Pillar 1 — Features that win BFSI clients (the priority)
What actually makes a bank/NBFC/insurer buy this, in priority order. (Implementation detail in the
workstreams below; the workstream tag in brackets is where each is built.)

**Deal-closing features (lead the pitch & the demo with these):**
1. **Verify-before-disclose (step-up auth)** [W2] — ask OTP / last-4 / KBA before revealing balances,
   loans, claims. Today anyone texting from a number is trusted — a bank will never buy that. *#1 feature.*
2. **Smart unknown-caller handling** [W2] — engage → ask back for a registered identifier (capped) →
   recover & verify a real customer, *or* capture an onboarding lead (revenue), *or* fraud-flag. Never
   blunt-reject. *(Manager idea #4.)*
3. **Voice as a channel** [W3] — voice/IVR is the #1 BFSI support channel; plugs into the same AI brain.
   *Top differentiator. (Idea #5.)*

**Ongoing customer-value features:**
4. **Proactive alerts & nudges** [W10] — EMI/premium due, card/KYC expiry, fraud & claim alerts (consent + throttle).
5. **AI cross-sell / next-best-action** [W10] — Neo4j already supports it; right product, right moment.
6. **Live agent console + AI-assist** [W6] — on handoff the human gets full context + suggested reply / summarise.
7. **Self-service transactions** [W10] — block a card, raise a dispute, get a statement (with step-up + dual control).

**Product-as-a-Service enablers (turn a bespoke build into a sellable product):**
8. **Multi-tenancy** [W1] — serve bank A *and* bank B on one platform; without it there is no PaaS business.
9. **Admin configurability** [W9] — clients self-configure intents/teams/SLAs/prompts instead of us coding per client.

> **Demo to lead with:** verify-before-disclose + the unknown-caller flow (engage → capped ask-back →
> recover / lead / fraud-flag). Visibly answers "what if someone we don't recognise reaches out."

## 3–8. Workstreams W1–W6 + cross-cutting

**W1 — Multi-tenant secure platform foundation** *(do first; without it nothing is sellable as PaaS)* — **L**
- `tenant_id` on every record/API/Neo4j-node/OpenSearch-index (`kb_{tenant}`)/queue msg; per-tenant
  config (branding, channels, credentials, KB, taxonomy, SLAs, languages).
- **Postgres** replaces SQLite (keep repo interface, swap driver; HA/backups/PITR).
- **Secrets manager** (Vault/KMS) vs `.env`; per-tenant credential vaulting.
- **Field-level PII encryption** (envelope, tenant-scoped keys); **RBAC** (admin/agent/supervisor/auditor);
  **data residency** (deploy-per-region, tenant flag).
- *Impl:* `TenantContext` threaded through `services/persistence_service/*` + migrations
  (`006_multitenant`, `007_postgres_*` / move to Alembic); tenant-resolution middleware in `apps/api`;
  `tenant_id` filter in `services/neo4j_service/queries.py`; per-tenant OpenSearch index;
  new `services/security_service/` (encryption + secrets client).

**W2 — Identity, auth & the "unregistered contact" problem** *(manager idea #4; #1 BFSI blocker)* — **L, highest after W1**
- *Problem:* `_resolve_identity → resolve_customer()` always resolves/**auto-creates**, then answers
  with that data — known customers trusted by number alone; unknowns silently created.
- **4 identity states** (replace binary found/created): `verified` (confirmed + step-up passed) ·
  `recognised_unverified` (known but not stepped-up → generic help, **no** account data) ·
  `unregistered` (no match, **not** auto-created) · `ambiguous` (>1 match → disambiguate).
- **Step-up engine** = new `verify_customer` node after `resolve_identity`, gating any node that surfaces
  account data. Risk-based (low-risk FAQ = none; data/transactional intents require it). Methods (per
  tenant/risk): OTP, knowledge-based (last-4/DOB/last txn), email magic-link, OIDC hand-off to bank IdP,
  optional voice biometrics (W3). Session token w/ TTL + sensitivity ceiling; lockout/throttle + fraud audit.
- **Unregistered handling (engage → identify → fallback, never blunt-reject):**
  1. **Engage** — greet and try to help; do not reject because the number/email is unknown.
  2. **Identify via capped ask-back loop** — solicit a registered identifier (mobile/email/customer ID) or a
     KYC fact (last-4 of account / DOB); **max 2–3 attempts** (anti-brute-force/enumeration). If a supplied
     identifier matches an existing customer (SQLite+Neo4j+CRM) → route into normal **step-up verification**
     and serve them. *(Rationale: an unknown sender is often a real customer on a new/work/family number —
     the ask-back recovers them instead of losing them.)*
  3. **Fallback (only after the loop fails to identify)** — branch on the **original query intent**:
     *onboarding/sales* ("open an account / apply for a loan") → treat as **new user → lead capture** →
     CRM lead + optional callback ticket (revenue); *account-access* ("my balance / my loan / my money") from
     an un-identifiable sender → **possible-fraud flag** + audit + optional silent fraud-team alert.
  - **Anti-enumeration throughout** — never confirm/deny whether an identifier belongs to a real customer to
    an unverified party. **Quarantine store** — unregistered interactions in a separate, retention-limited
    table; not merged into the customer graph until verified.
- **Improved validation:** `resolve_identity` returns confidence + match-evidence (which signals matched)
  not a bare record; cross-source corroboration (SQLite↔Neo4j↔CRM agree else `ambiguous`);
  family/shared-number disambiguation; feed outcome into escalation (unverified+sensitive → human ticket).
- *Impl:* new `services/identity_service/` (resolution + verification state machine); new graph nodes/edges
  + `state.py` fields (`identity_state`, `auth_level`, `verification_required`); gate the 4-tier retrieval on
  `auth_level`; tables `verification_attempts`, `unregistered_interactions`, `auth_sessions`.

**W3 — Voice as a channel** *(idea #5; top differentiator)* — **L** (phase biometrics as fast-follow)
- Inbound voice via SIP/telephony (Twilio/Exotel/Amazon Connect/Plivo — Exotel/Ozonetel help India
  residency) → ASR → **same pipeline** → TTS, streaming for low latency. IVR deflection + containment
  metrics; voice step-up (OTP-over-voice / biometrics, ties W2); barge-in/DTMF; Indic-language ASR;
  warm transfer w/ full AI context (W6); call recording + consent + transcript stored as `conversation_turns`
  (`channel='voice'`) so cross-channel continuity works.
- *Impl:* `services/voice_service/` + channel adapter normalizing ASR → existing `InboundMessage`;
  WebSocket/media-stream layer in `apps/api`; TTS rendering (voice tone: concise, no markdown, spell IDs)
  via `WorkflowAutomationAgent`; add `voice` to channel enum/analytics/audit.

**W4 — Data, consent & retention (DPDP/RBI)** *(builds on W1; G4/G5/G14)* — **M–L**
- Consent ledger (per purpose+channel; checked pre-processing; withdrawal honored) · retention engine
  (per-class TTL, auto-purge/anonymise, legal-hold) · data-subject rights API (export/correct/erase) ·
  immutable/hash-chained/WORM audit · centralized PII masking (logs, analytics, citations — extends the
  existing citation filtering) · KB governance (approval workflow, versioning, approved-source enforcement,
  freshness, admin UI) · data lineage (extends `retrieval_evidence`, surfaced for audit).

**W5 — AI governance, safety & quality** *(G9/G16; model governance)* — **M**
- Guardrail layer (in/out): prompt-injection/jailbreak defense · **PII/PAN redaction** before LLM & before
  logs · no-financial-advice guard · toxicity filter · hallucination/grounding check (ungrounded → escalate).
- Model registry/governance (versioned models+prompts, validation records, human-override, output logging,
  **drift monitoring**) · eval harness (golden-set: intent accuracy, faithfulness, refusal correctness,
  language quality; in CI; blocks regressions) · red-team suite (exfiltration, social-engineering,
  cross-tenant leakage, injection via email body) · confidence-aware UX + AI disclaimer · cost/latency budget.

**W6 — Operations: agent workspace, scale, observability** *(G7/G8/G10/G12)* — **L** (agent-console + infra sub-tracks)
- Async pipeline (queue Redis/RabbitMQ/SQS between ingestion + pipeline; worker pool; backpressure; durable
  outbound retry) · live agent console (unified inbox, full ticket context, AI-assist: suggested reply /
  summarise / draft-in-language / next-best-action-from-Neo4j, warm handoff, supervisor barge-in, compliant
  canned responses) · observability (OTel traces across the graph, Prometheus metrics, dashboards, alerting,
  SLO/error-budgets, cost-per-conversation, containment/automation KPIs) · DR/HA (backups, multi-AZ, runbooks,
  RTO/RPO) · CI/CD + IaC (Terraform, per-env pipelines, image scanning, SBOM).

**Cross-cutting — Configurability** *(W9)* — **M, high leverage; incrementally w/ W1.** Intents, teams, SLAs,
escalation/approval rules, prompts/persona, languages, channel credentials, branding all **admin-configurable**
(today hard-coded in `shared/constants/intents.py`, `services/workflow_service/*`, `orchestration_agents.py`)
+ no-code KB governance (W4). This is what makes onboarding the 2nd/3rd/10th client cheap — the PaaS margin.

**New feature ideas (#2, #3 — beyond gap-closing)** *(W10)* — proactive notifications & nudges (EMI/premium
due, low-balance, card/KYC-expiry, fraud/claim alerts; WhatsApp HSM + consent + throttle) · AI cross-sell /
next-best-action (Neo4j already supports candidate queries) · sentiment-driven churn/retention routing ·
self-service transactions w/ step-up (dispute, card block, statement, contact update — needs bank APIs +
dual-control) · conversational KYC/onboarding for leads · grievance & Ombudsman tracking w/ SLA clocks ·
voice-of-customer analytics (theme/complaint clustering — monetisable) · agent coaching/QA automation ·
customer-360 timeline in the agent console.

## 9. Pillar 2 — Compliance-readiness (the essential support)
The accelerator does **not** contain a bank's compliance program — it ships compliance **seams**
(interface + reference implementation + dev default) the bank plugs *their* controls into. The
**Compliance Matrix** (control → where it plugs in → evidence) is what shortens their security review,
and it's a sales asset. Buyers distrust vendors who claim to *be* their compliance — so we sell
"compliance-ready," not "compliance-hosted."

**Shared responsibility:**

| Control | Accelerator ships (the seam) | Bank / deployment owns |
|---|---|---|
| PII encryption | Field-encryption layer + pluggable KMS interface (dev key default) | Their KMS/HSM; they hold the keys |
| DPDP / consent | Consent ledger + pipeline checkpoint + "my-data" rights API | Purposes, retention periods, legal **Data-Fiduciary** accountability |
| Immutable audit | Append-only / hash-chained audit writer on every step | WORM/SIEM destination + retention schedule |
| Data residency | Stateless **deploy-per-region** topology + tenant region flag | Choice of region; runs in their cloud/VPC |
| AI governance | Model registry, eval harness, redaction, guardrails | Model-risk sign-off on the deployed instance |

**Regimes covered:** RBI (IT/cyber framework, IT-outsourcing 2023, digital-lending, grievance/Internal
Ombudsman SLAs, data localisation) · **DPDP 2023** (consent, purpose limitation, access/correction/
erasure, breach notification) · SEBI/IRDAI (retention, policyholder protection, claim timelines) ·
PCI-DSS (never store PAN/CVV) · GDPR (EU footprint) · ISO 27001 / SOC 2 Type II · AML/CFT & fraud audit
trails · model governance (RBI / SR 11-7 analogue) · accessibility (RBI + WCAG 2.1 AA).

> **What an accelerator cannot claim:** ISO/SOC2 certification (certifies an operating org, not code),
> pen-test sign-off (against the deployed instance), and DPDP legal accountability (the bank is the Data
> Fiduciary; we are the Data Processor). We *enable* all three; the bank *earns/owns* them.

## 10. Roadmap (4 increments, by dependency + deal-closing value)

| Increment | Theme | Workstreams | Why this order |
|---|---|---|---|
| **P2.1** | Trust & tenancy ("pass the bank's review") | W1 (tenant+Postgres+secrets+encryption+RBAC), W2 core, W4 audit+consent MVP, **W13/W14 guardrails** | Nothing sells without auth+tenancy+data protection; W2 is the best demo |
| **P2.2** | Omnichannel + governed AI | W3 (voice), W5 (guardrails+redaction+eval), W4 (retention+rights+KB gov), **W12 CX/UX** | Voice differentiates; guardrails are the must-have once reach expands |
| **P2.3** | Operate at scale | W6 (queue+agent console+observability+DR), W9 configurability | Production hardening + cheap multi-client onboarding |
| **P2.4** | Grow the account | W10 (proactive notifs, cross-sell/NBA, self-service, VoC, Ombudsman), **W11 metering** | Upsell once trusted + operable |

> **Demo to lead with:** W2 — a recognised-but-unverified customer is asked to verify before we show
> their loan status; an unknown sender is engaged, asked back for a registered identifier (capped), and
> either recovered + verified, captured as a lead, or fraud-flagged. Visibly answers idea #4.

## 12. Feature evaluation matrix (idea #3) — score 1–5 (5 best)

| Feature | Impact | Compliance | Feasibility | Verdict |
|---|:--:|:--:|:--:|---|
| Step-up auth + identity states (W2) | 5 | 5 | 3 | **Do first** — gating blocker + deal-maker |
| Unregistered-contact handling (W2) | 4 | 5 | 4 | **Do first** — explicit ask; fraud + lead value |
| Multi-tenancy + Postgres + secrets (W1) | 5 | 5 | 2 | **Do first** — foundational, highest effort |
| PII encryption + masking (W1/W4) | 3 | 5 | 3 | **Do first** — non-negotiable |
| Immutable audit + consent ledger (W4) | 3 | 5 | 3 | P2.1 |
| Voice channel (W3) | 5 | 3 | 2 | P2.2 — top differentiator |
| AI guardrails + PII redaction (W5) | 3 | 5 | 3 | P2.2 — required before wider exposure |
| Eval harness + model governance (W5) | 3 | 4 | 4 | P2.2 — cheap, big compliance signal |
| Data-subject rights + retention (W4) | 2 | 5 | 3 | P2.2 — DPDP mandatory |
| KB governance UI (W4) | 3 | 4 | 4 | P2.2 |
| Async queue + DR (W6) | 4 | 3 | 3 | P2.3 — production hardening |
| Live agent console + AI-assist (W6) | 5 | 3 | 3 | P2.3 — high value, larger build |
| Observability/SLO (W6) | 3 | 3 | 4 | P2.3 |
| Admin configurability (W9) | 4 | 2 | 3 | P2.3 — PaaS margin |
| Proactive notifications (W10) | 5 | 4 | 3 | P2.4 — revenue, consent-gated |
| Cross-sell / NBA (W10) | 5 | 3 | 4 | P2.4 — Neo4j already supports it |
| Self-service transactions (W10) | 5 | 5 | 2 | P2.4 — highest value+risk; needs bank APIs + dual control |
| VoC analytics (W10) | 3 | 1 | 4 | P2.4 — monetisable insight |
| Web chat / in-app SDK (G6) | 3 | 2 | 4 | Opportunistic — cheap channel reuse |

## 13. Risks & dependencies
- **Bank API access** (core banking, IdP, fraud, notification gateway) is on the client's critical path —
  start discovery early; clean adapter interfaces so we run "answer-only" until APIs are granted.
- **Voice provider + Indic ASR quality** — pilot 2; India-localised vendors help residency.
- **Model-risk sign-off** — engage the client's model-risk function early; eval harness + registry are the artifacts they want.
- **Effort concentration in W1/W2** — long poles; staff first.

## 14. One slide for the manager
1. **Pillar 1 — features that win the client:** verify-before-disclose, smart unknown-caller handling,
   **voice**, proactive alerts, cross-sell, agent console, self-service — on a **multi-tenant** platform
   (sell to bank A *and* B) that clients self-configure.
2. **Pillar 2 — compliance-ready, not compliance-hosted:** we ship the seams (encryption, consent/DPDP,
   immutable audit, residency) the bank plugs *their* KMS/SIEM/region into + a **Compliance Matrix** that
   shortens their audit. (DPDP, RBI, PCI, ISO/SOC2.)
3. Delivered as **14 workstreams** (W1 tenancy, W2 identity/step-up, W3 voice, W4 data/consent, W5 AI
   governance, W6 ops/agent-console, + W9 config, W10 revenue, W11 metering, W12 CX/UX, W13 QA, W14 platform-eng).
4. Sequencing: P2.1 pass-the-review → P2.2 omnichannel+governed-AI → P2.3 scale → P2.4 grow-the-account.
5. **Demo:** verify-before-disclose + the engage→ask-back→recover/lead/fraud-flag unknown-caller flow (W2).

## 15. Role-by-role completeness check
The first pass was written through a product/architecture lens. The brief assigns **seven roles**; each
flags mandatory items below, tagged with the workstream it folds into (**NEW** = creates one).

**Product Manager** — pricing/packaging (per-conv/per-seat/per-tenant + channel add-ons), usage metering,
billing, free-pilot → **NEW W11** · onboarding wizard + sandbox + golden-path (W9) · outcome KPIs
(containment, CSAT/NPS, FCR, cost-per-contact, deflection savings — we measure events not outcomes) (W6) ·
feature flags / A-B / beta cohorts (W5/W9) · competitive-parity checklist vs Sprinklr/Kore.ai/Yellow.ai/
Salesforce (W6/W10).

**UX/UI Designer** — customer-facing experience barely exists (only admin UI + thin portal); need branded
**WCAG 2.1 AA** experience across chat widget / in-app SDK / voice prompts / email templates → **NEW W12** ·
accessibility (screen-reader, contrast, font-scaling, keyboard nav, voice captions/transcripts — regulator-
relevant) · conversation design (flows, disambiguation, fallback recovery, step-up UX) · trust/transparency
UI (AI disclosure, verify-before-data screens, consent prompts, escalation messaging) · agent-console UX
(unified inbox, 360 timeline, AI-assist panel) · white-label theming (W9/W12) · localised UX (RTL, Indic
scripts, number/date/currency).

**Full-Stack Developer** — versioned public API (`/v1`) + OpenAPI + outbound webhooks + pagination +
idempotency on all writes (only inbound dedup today) + error envelope (W1/W6) · integration SDK / connector
framework (core-banking, IdP, fraud, notification, multi-CRM/telephony; today CRM is generic/Jira hard-wired)
(W1/W3) · event-driven backbone (outbox, event bus, replay) (W6) · concurrency (optimistic locking, race-safe
identity merge) (W1/W2) · performance (caching, pooling, async LLM, streaming) (W6) · managed migrations
(Alembic, rollback, multi-tenant-safe) (W1).

**QA Engineer** — almost no coverage (`test_phase1.py`, `test_user_portal.py`) + **no CI** (`.github` absent)
= release blocker → **NEW W13** · test pyramid (unit/integration/contract-per-connector/e2e-per-channel +
coverage gates) · AI testing (golden-set, non-determinism handling, prompt-drift regression — also W5) ·
safety/security suite (injection, cross-tenant leak, PII leak, authz bypass, anti-enumeration) (W5/W13) ·
non-functional (load/soak/stress for EMI-day/campaign spikes, latency-SLO, chaos/failover, DR drills) (W13/W6) ·
multilingual + a11y QA (W12/W13) · UAT + regulatory traceability matrix (req→test→evidence) (W13).

**DevOps/Cloud** — no CI/CD, no IaC, docker-compose only = not production-deployable → **NEW W14** · CI/CD
(build/test/scan/sign/deploy, dev→stg→prod, blue-green/canary, rollback) · IaC (Terraform/Helm/K8s, per-region/
per-tenant for residency) · supply-chain security (SBOM, image/dep scanning, signed artifacts, pinned deps,
hardened base) · externalised config + secret rotation (W1) · observability stack (central logs/metrics/traces,
dashboards, alerting, on-call/runbooks, **LLM cost monitoring**) (W6) · reliability (autoscale, HA, multi-AZ,
backup/restore, tested RTO/RPO, capacity planning) (W6/W14) · env/data segregation (prod data never in lower
envs; reuse `data/synthetic`) (W14).

**Business Analyst** — BRD/FRD + BFSI process mapping (dispute/claim lifecycle, grievance/Ombudsman SLA clock,
KYC re-verification) as configurable workflows (W9) · ROI/business-case calculator (deflection savings, agent
productivity, CSAT) (W11/sales) · regulatory SLA modelling (RBI/IRDAI timelines + Ombudsman auto-escalation)
(W4/W9) · operational/compliance/exec dashboards + scheduled regulatory reports + audit packs (W6) · data
dictionary + classification (PII/sensitive/financial) + lineage (extends `retrieval_evidence`) (W4) · change
management + training material/runbooks/admin guides (W9).

**Security Engineer** — STRIDE threat model + secure SDLC + SAST/DAST/dep-scan in CI + pre-go-live pen-test
(W5/W13/W14) · authN/Z hardening (SSO/OIDC, admin/agent MFA, least-privilege RBAC, scoped tokens, key rotation;
single API key today insufficient) (W1) · API security (**rate limiting/throttling — absent today**, WAF, input
validation, webhook anti-automation, replay protection beyond dedup) (W1/W6) · tenant isolation as a tested
security boundary (row-level security, per-tenant keys, isolation tests) (W1/W13) · PII/PAN protection
(field-level encryption, tokenisation, centralized redaction, UI masking, **PCI scope minimisation — never store
PAN/CVV**) (W4/W5) · AI security (injection/jailbreak defense, output filtering, tool/action authorisation for
self-service, exfiltration guards) (W5) · audit/monitoring/IR (tamper-evident audit, SIEM, anomaly/fraud
detection, **incident-response + breach-notification (DPDP)**) (W4/W6) · certifications path (ISO 27001 / SOC 2
+ evidence; answer CAIQ/VSA) (W4/W14) · fraud controls (velocity checks, device/number reputation, anomaly-
triggered step-up, maker-checker for sensitive actions) (W2/W10).

**Workstreams produced by this review:** **W11** Monetisation & metering (PM/BA — no PaaS without it) ·
**W12** Customer CX/UX & accessibility (UX — customer experience barely exists; WCAG regulator-relevant) ·
**W13** Quality & test automation (QA/Security — near-zero tests + no CI) · **W14** Platform engineering
(DevOps/Security — docker-compose only, not deployable/auditable). W13/W14 start in P2.1 as guardrails;
W12 lands in P2.2; W11 in P2.4.

**Mandatory go-live checklist (the "nothing left out" list)**
- *Trust & security:* SSO/MFA · RBAC · tested tenant isolation · field-level PII encryption · secrets manager
  + rotation · rate limiting/WAF · PCI scope minimisation · threat model · SAST/DAST/dep+image scanning ·
  pen-test · SIEM + IR + breach notification.
- *Identity:* step-up verification · risk-based auth · unregistered handling · anti-enumeration · fraud/velocity
  controls · maker-checker for sensitive actions.
- *Compliance:* DPDP consent + rights + retention/erasure · RBI/IRDAI grievance & Ombudsman SLAs · immutable
  audit · data residency · model governance (registry/eval/drift/human-override) · ISO 27001 / SOC 2 evidence.
- *Channels & CX:* WhatsApp · Email · **Voice/IVR** · web chat / in-app SDK · WCAG 2.1 AA · conversation design ·
  localisation (Indic/RTL) · white-label theming · AI-disclosure & consent UX.
- *AI governance:* PII/PAN redaction · injection/jailbreak defense · no-financial-advice guard · grounding check ·
  eval harness + red-team in CI.
- *Operations:* Postgres HA + backup/PITR · async queue + workers · autoscale/HA/multi-AZ · DR w/ tested RTO/RPO ·
  OTel traces+metrics+alerting+SLOs · LLM cost monitoring · agent console + AI-assist + warm handoff + supervisor tools.
- *Productisation:* admin-configurable taxonomy/routing/SLA/prompts · KB governance · onboarding wizard + sandbox ·
  usage metering + billing + packaging · business/compliance/exec dashboards · ROI model.
