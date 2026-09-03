# Omnichannel CX Solution Approach - Production Scope - BFSI

## 1. Overview

Our Omnichannel CX accelerator is a working AI-led customer support platform built for the
BFSI domain. It demonstrates the capabilities that matter most in regulated customer
service: a single view of the customer across every channel, continuity of a case as it
moves between channels and over time, answers grounded strictly in approved knowledge and
the customer's own records, and a controlled decision about when a human must take over.

This document sets out how that accelerator translates into a production deployment for a
bank, NBFC or insurer. It is organised in three columns throughout:

| Column | Meaning |
|---|---|
| **Capability** | The capability under discussion |
| **Accelerator demonstrates** | What is already built and working in the accelerator |
| **Production scope** | What a full production deployment adds |

---

## 2. What the accelerator already demonstrates

These capabilities are working in a running system, not design intent. The platform is
deliberately hybrid: language models handle understanding and generation, while identity,
data retrieval, safety floors and audit are deterministic code. The last column states which
applies, because in a regulated environment it matters whether a decision is probabilistic
or guaranteed.

| Capability | What it does | AI / deterministic |
|---|---|---|
| **Omnichannel identity** | An email address or phone number resolves to one verified customer record whichever channel it arrives on, including country-code variants of the same number. Contacts that match no real customer are identified as unregistered and never served invented holdings or history | Deterministic |
| **Customer 360 knowledge graph** | Accounts, deposits, cards, loans, policies, claims, charges, transactions and open cases are held as a connected graph and retrieved as trusted context for every interaction | Deterministic |
| **Case continuity** | Messages arriving days apart on different channels are grouped into the same case. A referee model decides whether a new message belongs to an existing case by reading what it says, rather than matching keywords | AI referee; graph relationships are the authority |
| **Triage** | Every message is classified into one of sixteen BFSI intents with a confidence score and stated reason, plus urgency, sentiment and language. The classifier reads the last five turns in both directions, so it understands messages that only make sense in context | AI, with rule-based fallback |
| **Grounded answering** | Replies are composed only from approved knowledge-base content and the customer's own verified records. Balances, cards, loans, claims and transactions are answered from the customer's actual data, with figures carrying their own qualifiers. The system states what it does not know rather than filling the gap | AI generation over deterministic retrieval |
| **Knowledge retrieval** | Hybrid vector and keyword search over the approved knowledge base, using a locally hosted embedding model so document content never leaves the environment for indexing | Deterministic; local model |
| **Human-in-the-loop** | Before any reply is sent, three independent layers decide whether a person must see it first: rule-based escalation over resolution level, intent, confidence and retrieval strength; an AI check that reads the customer's actual words rather than their category label, returning a closed reason set (asked for a human, asserting we already failed them, emergency, distress, needs a decision) and running ahead of the rules that would otherwise exempt the message; and a deterministic pattern floor for explicit human requests that holds even when the model is unavailable. On a hold the AI's reply is not sent - it becomes an editable draft in a review queue labelled with the reason, the customer receives an acknowledgement, and the agent edits and sends | Deterministic gate; AI judgement inside it |
| **Multilingual** | The customer's language is detected from their message and the reply is generated in that language | AI |
| **Agent assist** | The agent picking up a case sees a generated case summary, next-best-action recommendations filtered to open cases, and the retrieved evidence behind each AI answer so it can be verified before sending | AI summary; rule-based recommendations |
| **Cross-sell and up-sell** | Opportunities are identified from what the customer actually holds - a premium-segment customer on an entry-level card, repeated penalty charges a different tier would waive, a product family they have been asking about - and suppressed entirely when sentiment is negative | Rule-based identification; AI drafts the wording |
| **Traceability** | Nine distinct AI operations run across the platform and each is individually recorded with its token usage and configuration version. Retrieval evidence is stored per answer, and conversations, cases and decisions are captured as auditable events | Deterministic |
| **PII protection** | PAN, Aadhaar, phone, email and card numbers are detected and masked before any text reaches an external model provider, by pattern and by exact match against known customer values | Deterministic |
| **Channels** | Email, WhatsApp and web chat all enter the same orchestration pipeline, so triage, case grouping and behaviour are identical regardless of how the customer made contact | Deterministic |

## 3. Customer journey in production

### 3.1 Identity and channels

| Capability | Accelerator demonstrates | Production scope |
|---|---|---|
| Customer identification | Phone and email resolve to one verified customer record across all channels; unrecognised contacts handled safely | Core banking CIF as the system of authority |
| Authentication | Authenticated portal access | Step-up authentication before disclosure or any value-bearing action |
| Third-party authority | - | Joint holders, power of attorney, guardians and corporate signatories |
| Email, WhatsApp, web chat | Live on all three, unified into one pipeline | Enterprise mail infrastructure, business-verified WhatsApp with approved templates, pre-login chat |
| Voice | - | IVR and CTI integration, speech-to-text and text-to-speech, call recording with mandated retention |
| Cross-channel continuity | A case follows the customer between channels | Extended to voice, so a call continues an existing chat or email thread |

### 3.2 Triage, answering and escalation

| Capability | Accelerator demonstrates | Production scope |
|---|---|---|
| Triage | Intent, urgency, sentiment, language, confidence and customer context on every message | Taxonomy extended to the client's products and grievance categories; confidence calibrated against measured accuracy |
| Routing dimensions | Resolution level drives escalation | Adds explicit complexity and safety-boundary judgement, persisted customer preference, and policy rules mandating human approval for defined request types |
| Answering | Grounded in approved knowledge and the customer's own records, across balances, cards, loans, policies, claims and transactions | Knowledge scoped by entity, product and language; extended across the client's full product set |
| Regulated advice | Restricted by design | Hard guardrail with abstention and routing to an authorised person |
| Escalation decision | Rule engine plus a check that reads the customer's own words, so a genuine complaint is held even when its category looks routine | Retained as a core strength |
| Escalation routing | Three-level classification assigns a level | Skills-based routing to named queues and individuals, with a named owner per escalation level |
| Grievance framework | - | Regulator-aligned categories, redressal timelines, Nodal Officer routing and Ombudsman escalation |

### 3.3 Actions and case management

| Capability | Accelerator demonstrates | Production scope |
|---|---|---|
| Service actions | Case creation and routing | Card block and replacement, dispute initiation, PIN reset, cheque stop, contact update, travel notice, statement request, callback booking |
| Autonomy model | Answers autonomously; holds for a human when the message warrants it | Extended to actions: execute when low-risk, clarify when ambiguous, defer when the backing system is unavailable |
| Maker-checker | Reply drafts held for human approval | Extended to transactions: value-bearing actions require human authorisation regardless of AI confidence |
| Case lifecycle | Automatic case creation with AI-refereed grouping; open, logged and closed states | Full lifecycle with defined transitions, ownership and reopen handling |
| Disposition | Case status and escalation reason recorded | Controlled disposition taxonomy driving first-contact resolution, containment and regulatory reporting |
| SLA and TAT | - | Per-category clocks with breach alerting |

### 3.4 Agent assist and proactive engagement

| Capability | Accelerator demonstrates | Production scope |
|---|---|---|
| Live assist | Case summary, next-best-action and retrieved evidence surfaced to the agent | Extended to live voice conversations |
| Handover context | Identity, channel, language, intent, summary, confidence, evidence and escalation reason travel with the case | Adds actions already completed, outstanding questions and recommended next action |
| Post-handover monitoring | Assist continues after handover | Intent-change and sentiment-deterioration detection, recommended disposition |
| Accountability | The human sends the reply on held drafts | Retained - the human remains accountable for the customer-facing action |
| Outbound campaigns | - | Payment and EMI reminders, mandate bounce alerts, KYC expiry, card renewal, deposit maturity, dormant reactivation, escalating from message to call |
| Consent and contact governance | - | Purpose-bound consent, do-not-contact enforcement, permitted hours, frequency caps and full campaign audit |

## 4. Data platform

Production deployment integrates with the client's existing systems rather than replacing
them.

### 4.1 Source systems

| Source | Data |
|---|---|
| Core banking | Customers, accounts, balances, transactions |
| Cards | Limits, dues, statements |
| Loans | Applications, schedules, delinquency |
| Policy administration and claims | Policies, claims, servicing events |
| CRM | Cases, interactions, dispositions |
| Telephony / CTI | Call events, recordings, metadata |
| Payments and disputes | Chargebacks, settlement status |

Ingestion is selected per source: change data capture for transactional systems requiring
near-real-time currency, batch for reference and reconciliation data, and event streaming
for interaction telemetry.

### 4.2 Architecture on AWS

| Layer | Service | Purpose |
|---|---|---|
| Landing | S3 | Immutable arrival of source extracts and events |
| Streaming ingest | MSK or Kinesis | Interaction events and CDC streams |
| Transformation | Glue | Normalisation, conformance and PII handling |
| Curated lakehouse | S3 with Glue Catalog (Iceberg) | Conformed customer, account, interaction and case entities |
| Operational store | RDS PostgreSQL, Multi-AZ | Transactional system of record |
| Knowledge graph | Neptune, or Neo4j on EKS | Customer 360 and case continuity |
| Search and vector | Amazon OpenSearch Service | Knowledge retrieval |
| Analytics | Athena and Redshift | Contact-centre MI and regulatory reporting |
| Orchestration | Step Functions or MWAA | Pipeline scheduling |

### 4.3 Immutability, quality and reporting

- **Append-only record.** Customer-facing statements and decisions are recorded immutably. Corrections append as new timestamped records so the position at any past date can be reconstructed for audit
- **Data quality.** Validation and quarantine at ingestion, reconciliation against source control totals, field-level lineage from source to any figure quoted to a customer, and freshness monitoring per feed
- **Reporting.** Contact-centre MI by channel and category, regulatory grievance reporting, AI performance reporting, and business outcome measurement covering conversion, retention and cost-to-serve

---

## 5. Cloud and infrastructure (AWS)

| Component | Target |
|---|---|
| Application | ECS Fargate or EKS, multi-AZ, behind an Application Load Balancer |
| Edge | API Gateway or ALB with WAF |
| Data stores | RDS Multi-AZ, OpenSearch Service, Neptune - all in private subnets |
| Secrets | AWS Secrets Manager with rotation |
| Asynchronous processing | SQS for outbound delivery and long-running work |
| Scheduling | EventBridge for proactive engagement cadences |

**Security.** TLS in transit and KMS-managed encryption at rest across all stores;
least-privilege IAM roles per service; deployment in an Indian region with data localisation
for payment data; PII masked before any text leaves the client boundary; penetration testing
and vulnerability scanning before go-live.

**Availability and continuity.** Multi-AZ as the baseline, horizontal scaling of stateless
services, queue-backed outbound delivery, agreed RPO and RTO with tested restore, cross-region
backup and a documented failover runbook.

**Delivery.** Separate development, UAT and production accounts; infrastructure as code;
CI/CD with automated testing and controlled promotion; blue-green or canary release with
rollback.

---

## 6. AI platform and operations

| Capability | Accelerator demonstrates | Production scope |
|---|---|---|
| Model strategy | Configurable model provider | Multi-model strategy with automatic failover; Amazon Bedrock for in-account inference and data-residency alignment |
| Resilience | Bounded call timeouts with safe fallback behaviour | Retry with backoff, circuit breaking and graceful degradation to a deterministic path |
| Throughput and cost | Per-call token and cost accounting on every operation | Capacity modelled against contact volumes, with provisioned throughput and per-interaction cost budgets |
| Prompt and model governance | Prompt configuration versioned per call | Prompts and model versions managed as controlled, releasable artefacts with regression testing and rollback |
| Observability | Full tracing of AI decisions, retrievals and model calls | Centralised logging and metrics, latency and error-rate alerting, defined severities and on-call runbooks |

---

## 7. Knowledge governance

Knowledge control is a first-class requirement in BFSI: interest rates, fee schedules and
product terms change on defined dates, and serving superseded terms carries regulatory
exposure.

| Control | Production requirement |
|---|---|
| Ownership | Named business owner for each knowledge domain |
| Approval | Business, compliance and legal sign-off before publication |
| Version and effective date | Real version identifiers, with effective and expiry dates |
| Expiry | Superseded content blocked from retrieval, not merely deprioritised |
| Scope | Applicability by entity, product, geography and language |
| Traceability | Every answer traceable to the retrieved source that supports it |
| Change management | Changes tested in a lower environment before production use |
| Rollback | Ability to revert a knowledge, prompt or model release |

---

## 8. AI assurance and evaluation

A production deployment is governed by measured performance against agreed targets. For each
metric the engagement defines the formula, the evaluation sample, the target and the
confidence interval.

| Metric | Measures |
|---|---|
| Intent accuracy | Correct classification against a labelled set |
| Retrieval relevance | Quality of retrieved evidence |
| Groundedness | Whether answers are supported by retrieved sources |
| Hallucination rate | Unsupported content, detected and bounded |
| Safe-abstention rate | Correct refusals as a share of opportunities to refuse |
| Escalation accuracy | Correct handover decisions |
| Containment rate | Interactions safely completed without transfer |
| Response latency | P50, P95 and P99 by channel |
| Language accuracy | Performance per language, not aggregate |
| Disposition accuracy | Correct outcome coding |
| Follow-up completion | Proactive tasks completed within TAT |
| Feedback recovery | Negative-feedback cases recovered and closed |

Establishing a **labelled evaluation set** with the client's own subject-matter experts is a
defined early deliverable; the groundedness, hallucination and abstention measures depend on
it. A feedback loop ingests CSAT, NPS and complaint signals, triggers a recovery workflow
below an agreed threshold, and feeds quality findings back into knowledge and model
improvement.

Performance is expected to improve materially between early operation and steady state.
The engagement therefore begins with tight monitoring and conservative automation
thresholds, relaxing them as measured performance justifies it.

---

## 9. Regulatory and compliance

| Requirement | Production scope |
|---|---|
| Grievance redressal | Regulator-aligned categories, defined redressal timelines, Nodal and Principal Nodal Officer routing, Ombudsman escalation |
| Financial advice | Hard guardrail with abstention and routing to an authorised person |
| Data protection | Purpose-bound consent capture and enforcement under the DPDP Act |
| Data residency | Indian region deployment with localisation for payment data |
| Retention and erasure | Retention schedules reconciled against erasure rights and mandated financial record-keeping |
| Audit | Immutable record of customer-facing statements and the basis for each |
| Contact governance | Do-not-contact enforcement, permitted hours and frequency caps |
| Call recording | Recording, consent notification and mandated retention |
| Fraud response | Time-bound handling for suspected unauthorised transactions |
| Explainability | Every AI decision traceable to its evidence and inputs |

---

## 10. Multi-entity rollout

Groups operating multiple entities, brands or business units - each with its own core
system, telephony and customer base - are supported through a repeatable rollout pattern.

| Capability | Production scope |
|---|---|
| Tenancy | Isolation of data, knowledge, configuration and reporting per entity |
| Configuration | Per-entity rules, escalation matrices, templates and thresholds |
| Knowledge scoping | Knowledge bases scoped by entity, product and language |
| Onboarding | Repeatable sequence: integrate core systems, load and approve knowledge, configure routing, evaluate against agreed targets, go live |

The recommended approach is to prove the platform end-to-end at one flagship entity, then
replicate. Each subsequent rollout reuses the integration patterns, knowledge structure and
evaluation framework established in the first.

---

## 11. Delivery approach

| Phase | Scope |
|---|---|
| **1. Foundation** | AWS landing zone, infrastructure as code and CI/CD; core system integrations; production data stores; observability and alerting |
| **2. Compliance baseline** | Grievance framework with named ownership and timelines; knowledge governance with approval, versioning and expiry; consent and contact governance; step-up authentication; disposition taxonomy |
| **3. Capability build** | Voice channel; service actions with maker-checker authorisation; proactive engagement; evaluation framework and labelled evaluation set |
| **4. Scale** | Additional entities; analytics and reporting; performance testing and capacity validation |

Effort and duration are established during discovery, and depend on the client's core system
access, telephony landscape and cloud maturity.
