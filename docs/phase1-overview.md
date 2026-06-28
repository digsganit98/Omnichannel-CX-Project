# Phase 1 — Omnichannel CX Accelerator (BFSI)

> Current state of the repo, written from the **source code** (not the stale `README.md`,
> which still describes an earlier e-commerce version). Where they disagree, the code wins.

## 1. Purpose
A local, Docker-based, AI-powered omnichannel customer-support system for **BFSI** (Banking,
Financial Services & Insurance). It takes an inbound message on **WhatsApp or Email**, runs a
multi-agent AI pipeline, and either **auto-answers** (using the customer's own data in Neo4j +
an approved RAG knowledge base) or **escalates to a support ticket** — maintaining a single,
continuous **cross-channel conversation** per customer. Operated via a browser **admin UI** and
a customer-facing **user portal**.

## 2. Features

**Channels & messaging**
- **WhatsApp** — inbound via Meta Cloud webhook (`/integrations/whatsapp/webhook`, validates
  `x-hub-signature-256` against `WHATSAPP_APP_SECRET`); local-test simulator
  (`/test/whatsapp/inbound-simulate`, `/test/whatsapp/send`); outbound via Meta Cloud API or log connector.
- **Email** — inbound via authenticated webhook (`/integrations/email/webhook`, `/webhooks/email`);
  optional **IMAP polling** (Gmail) on startup when `IMAP_ENABLED=true`; outbound via SMTP (Gmail/Mailpit).
- **Cross-channel continuity** — phone + email link to one identity; WhatsApp/email turns share one
  thread; the LLM acknowledges prior-channel context without re-asking.
- **Idempotency** — a repeated provider `message_id` returns the cached response.
- **Outbound delivery** — modes `log` / `live`, with retry/backoff (3 attempts).

**AI understanding**
- **Intent classification** over a **16-intent BFSI taxonomy** via **Groq LLM** + deterministic
  keyword **rule fallback**. Guardrails: rules override the LLM on boundary cases when the LLM is
  uncertain (`<0.65`) and the rule classifier is confident (`>0.70`); rules escalate sentiment/urgency.
- **Sentiment** (pos/neutral/neg), **urgency** (low/med/high), **secondary/compound intent** (e.g.
  "check loan AND report fraud" → second ticket), **multilingual** (Hindi/Tamil/Telugu/Kannada…
  detect + reply in-language), **disambiguation** (e.g. "applied weeks ago, any update?" →
  `loan_status` not `loan_application`; mirror for `claim_status` vs `insurance_claim`).
- **The 16 intents:** `account_balance_inquiry`, `transaction_dispute`, `fund_transfer`,
  `loan_status`, `loan_application`, `loan_default_notice`, `policy_status`, `claim_status`,
  `insurance_claim`, `card_management`, `kyc_update`, `fraud_report`, `complaint`,
  `ticket_status`, `general_inquiry`, `human_escalation`.

**Answer generation (4-tier layered retrieval, highest-priority source wins)**
1. **Resolution Memory cache** (Neo4j) — agent-verified reusable answers for non-sensitive intents.
2. **Ticket-status lookup** — NL summary of the customer's open tickets.
3. **Neo4j customer graph** — real transactional data (loan/claim/policy), read through the LLM.
4. **RAG / KB** — semantic search over approved KB docs (OpenSearch) + keyword/hybrid fallback + re-ranking.

All KB answers carry **citations**; only `knowledge_base`-typed contexts are surfaced
(customer-safe filtering excludes profile/transactional data from citations).

**Ticketing & escalation**
- **Lifecycle** — `open → in_progress → resolved`; priority low/med/high; SLA due date; assigned
  team; escalation reason; approval status.
- **Escalation policy** (`services/agent_service/orchestration_agents.py`): explicit human request;
  manual-review intents (fraud report, transaction dispute, loan default notice, complaint, human
  escalation); no live banking data (`account_balance_inquiry`, `fund_transfer`); repeated unresolved
  query; high urgency; low intent confidence (`<0.6`); repeat customer w/ new issue; knowledge-not-found;
  low retrieval confidence (`<0.3`). Pure informational intents (`loan_status`, `claim_status`,
  `policy_status`) never create a ticket on their own.
- **Team routing** (`shared/constants/intents.py`) — e.g. `fraud_report → fraud_and_disputes`,
  `loan_status → loans`, `kyc_update → compliance`, `card_management → card_services`.
- **Customer-driven closure** — "close the ticket, thanks" detected by keyword rules + LLM fallback.
- **Optional CRM/Jira Cloud sync** — create/comment/transition; tracks `external_ticket_id`/URL/status;
  manual re-sync. Off by default (`CRM_PROVIDER=disabled`).

**Customer graph (Neo4j)** — seeded from `data/bfsi.xlsx` on startup: nodes `Customer`, `Loan`,
`Claim`, `Policy`, `Product`, `KYC`, `Agent`; rels `HAS_LOAN`, `HAS_CLAIM`, `HAS_POLICY`,
`KYC_VERIFIED_BY`, `PRODUCT_IS`. Writes `Interaction` nodes in two phases (open on receipt, closed
post-pipeline) + `ResolutionMemory`. Used for identity linking, customer-360, cross-sell.

**Portals & UI**
- **Admin UI** (`/admin-ui`) — CRM status, ticket queue/detail/comments/status, manual sync, WhatsApp
  & Email simulators, audit feed, raw orchestration JSON.
- **User portal** (`/user/...`) — signup/login (JWT), send message through the same pipeline, view own
  tickets/conversations.
- **Admin auth** (`/admin/auth/...`) — key verify, signup/login, user listing, change-password.
- **Analytics** (`/analytics/...`) — overview KPIs, by-channel/intent, sentiment, per-agent, ticket
  trend, realtime SSE event stream.

**Observability & governance** — audit events per workflow step; structured JSON logging + HTTP
latency middleware; workflow trace returned in every response; retrieval evidence persisted per turn.

## 3. Technicalities

**Stack:** Python 3.13 · FastAPI 0.115 + Uvicorn · Pydantic v2 · **LangGraph 0.2.76** (`StateGraph`) ·
primary LLM **Groq** `llama-3.1-8b-instant` (temp 0.2) · local LLM **Ollama** `qwen2.5:0.5b` ·
embeddings sentence-transformers 3.3 (`all-MiniLM-L6-v2`, Torch CPU) · vector store **OpenSearch 2.17** ·
graph **Neo4j 5** (+ openpyxl Excel seed) · system-of-record **SQLite** (Docker volume `cx-data`) ·
auth PyJWT HS256 + PBKDF2-SHA256 · httpx, pypdf.

**Orchestration (LangGraph)** — `services/orchestration_service/graph.py`; engine `langgraph_state_graph`:
```
receive_message → resolve_identity → load_conversation_context → detect_ticket_action
   → (conditional) resolve_ticket | classify_intent
classify_intent → resolve_query → decide_ticket
   → (conditional) create_ticket | skip_ticket
   → send_outbound_reply → persist_audit_events → END
(resolve_ticket also → send_outbound_reply)
```
**Named agents** (`services/agent_service/orchestration_agents.py`):
1. `IntentClassificationAgent` — classify + Neo4j enrich + post-classification fixes.
2. `QueryResolutionAgent` — the 4-tier retrieval (memory → tickets → Neo4j → RAG).
3. `TicketCreationAgent` — escalation decision, create/resolve, close-action detection.
Plus `WorkflowAutomationAgent` (infra) — composes channel-specific reply + outbound delivery.

**Data layer (SQLite)** — tables: `customers`, `channel_identities` (unique per `channel`+`identifier`),
`conversations`, `conversation_turns`, `tickets`, `ticket_events`, `idempotency_keys`, `audit_events`,
`retrieval_evidence`. Migrations `001_phase1.sql` … `005_customer_users.sql` applied on container start
(`python -m services.persistence_service.migrate`).

**Workflow services** (`services/workflow_service/`) — `assignment.py` (intent→team), `sla.py` (SLA hours
by priority), `approvals.py` (which intents need approval), `escalation.py`, `automations.py`, `status_engine.py`.

**API surface (by prefix)**
- Public: `GET|POST /integrations/whatsapp/webhook`, `POST /integrations/email/webhook`, `POST /webhooks/email`
- Test: `POST /test/whatsapp/inbound-simulate`, `POST /test/whatsapp/send`
- User (`/user`): `auth/login`, `auth/signup`, `messages`, `GET tickets`, `GET tickets/{conversation_id}`
- Admin auth: `verify-key`, `signup`, `login`, `GET users`, `change-password`
- Admin (`x-admin-key`): Tickets `/admin/tickets` (`GET`, `GET/{id}`, `GET/{id}/events`, `POST/{id}/sync`,
  `POST/{id}/comments`, `PATCH/{id}/status`); `GET /admin/conversations[/{id}]`; `GET /admin/audit-events`;
  `GET /admin/crm/status`; `/admin/email` (`GET status`, `POST test-send`); `/admin/email-inbox`
  (`GET status`, `POST poll`); RAG `/admin/rag` (`GET health`, `POST index`, `POST query`, `GET diagnostics`);
  WhatsApp `/admin/whatsapp` (`GET status`, `GET delivery-statuses`); Orchestration `/admin/orchestration`
  (`GET workflow`, `GET ai-runtime`); Neo4j `/admin/neo4j` (`POST load`, `GET status`, `POST setup-indexes`,
  `GET cross-sell-candidates`); Customers `GET /admin/customers/{id}/graph`
- Analytics (`/analytics`): `overview`, `channels`, `intents`, `sentiment`, `agents`, `trend`, `events`, `stream`
- Health: `GET /`, `GET /health`

**Security** — admin API key (`x-admin-key`); email webhook secret (`x-email-webhook-secret`); WhatsApp
local-test signature + verify token; production WhatsApp webhook validates `x-hub-signature-256` (HMAC w/
`WHATSAPP_APP_SECRET`); JWT for user portal + analytics.

**Infrastructure** (`docker-compose.yml`) — `api` (8888→8000), `opensearch` (9200), `ollama` (11434),
`ollama-pull` (setup profile), `neo4j` (7474, 7687), `mailpit` (1025, 8025), `ngrok` (4040). Volumes:
`cx-data`, `opensearch-data`, `ollama-data`, `huggingface-cache`, `neo4j-data`.
> App listens on container **8000**, mapped to host **8888** (`http://localhost:8888`).

**Prompt engineering** — central system prompt (`shared/prompts/system.md`): BFSI persona; channel tone
(WhatsApp brief, Email formal); cross-channel continuity; anti-hallucination (no invented IDs/timelines,
mask sensitive identifiers, never name internal systems); escalation/sensitive handling. Generator prompts
(`services/rag_service/groq_generator.py`) add channel-format + language rules + few-shot examples + graph/conversation context.
