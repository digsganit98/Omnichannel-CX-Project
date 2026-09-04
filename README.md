# Omnichannel CX Accelerator

A local, Docker-based customer support system for BFSI (banking, financial services and
insurance). A customer writes in on WhatsApp, email or web chat; the system works out who they
are, reads their account records out of a graph database, answers the question, decides whether
a human needs to see the reply before it is sent, and keeps every message on one continuous
thread regardless of which channel it arrived on.

Two surfaces run on the same backend:

| Surface | Who uses it |
|---|---|
| Agent console | Support agents and admins |
| Customer portal | Customers (web chat) |

Both live at **http://localhost:8888/admin-ui** — the sign-in screen offers an **Admin** and a
**User** tab, and the one you pick decides which surface loads.

> **The API is on host port 8888**, mapped to 8000 inside the container
> (`"8888:8000"` in `docker-compose.yml`). Older docs saying 8000 are wrong.

---

## What makes this different

**One customer, one conversation, every channel.** A question asked on WhatsApp and followed up
by email is the same thread, on the same ticket, with the same history — because identity is
resolved across phone, email and portal login onto a single customer record.

**Answers come from the customer's own records, not from a template.** The reply path walks the
customer's subgraph in Neo4j and hands the model whatever is actually there — accounts, cards,
loans, fixed deposits, claims, policies, transactions, KYC, charges. There is no hand-written
list of fields, so a new property in the seed data shows up in answers with no code change.

**A knowledge base sits alongside it.** Process questions ("how do I file a claim?") are answered
from indexed documents in OpenSearch, and both sources can reach the model on the same message.

**The system decides when a human is needed.** Several rules run before a reply is sent — credible
risk, escalating intents, weak retrieval, and a check that reads the customer's actual words
rather than a category label. Held replies land in the agent console as an editable draft.

**It learns from what agents do.** When an agent sends a drafted reply unedited, that answer is
marked verified in the graph and can be reused for the same kind of problem later.

---

## Architecture

```text
  WhatsApp          Email           Web chat
  (Meta Cloud)      (IMAP/SMTP)     (portal)
      |                 |                |
      +--------- channel adapters -------+
                        |
                normalized InboundMessage
                        |
                 LangGraph orchestration
                        |
   +--------------------+---------------------+
   |          |            |          |        |
 identity  intent      retrieval   ticket   delivery
 (SQLite)  (Groq)   (Neo4j + KB)  decision  (+ review)
                        |
                 reply, or a draft held for an agent
```

**The pipeline is channel-agnostic.** Each channel has one adapter with a single `normalize()`
method; everything downstream — intent, retrieval, tickets, escalation, analytics — never asks
which channel a message came from.

### Where things live

| Concern | Path |
|---|---|
| LangGraph workflow | `services/orchestration_service/graph.py` |
| Agent logic | `services/agent_service/orchestration_agents.py` |
| Human-handoff check | `services/agent_service/handoff.py` |
| Review / hold gate | `services/workflow_service/review_gate.py` |
| Graph queries | `services/neo4j_service/` |
| RAG / knowledge base | `services/rag_service/` |
| LLM generation (Groq) | `services/rag_service/groq_generator.py` |
| Channel adapters | `services/channel_service/adapters/` |
| Outbound delivery | `services/channel_service/delivery.py` |
| Persistence | `services/persistence_service/repository.py` |
| API routes | `apps/api/routes/` |
| Both UIs (single page app) | `apps/admin-ui/` |
| System prompt | `shared/prompts/system.md` |

---

## The message pipeline

`services/orchestration_service/graph.py` builds a LangGraph state machine. In order:

1. **receive_message** — normalize and record the inbound turn
2. **resolve_identity** — match phone / email / portal login to one customer
3. **load_conversation_context** — prior turns across all channels
4. **check_has_open_case** — settle the customer's case state once, before the message is read
5. **detect_ticket_action** — is this closing an existing ticket?
6. **classify_intent** — one of 16 intents, with confidence and urgency
7. **validate_customer** — unregistered senders are rejected, never given invented data
8. **resolve_query** — graph records and/or knowledge base, then generate the answer
9. **decide_ticket** — every query gets a ticket; the rules decide whether it is *held*
10. **send_outbound_reply** — deliver, or hold as a draft for an agent
11. **persist_audit_events** — audit trail, evidence, LLM usage

### Intents

`account_balance_inquiry`, `transaction_dispute`, `fund_transfer`, `loan_status`,
`loan_application`, `loan_default_notice`, `policy_status`, `claim_status`, `insurance_claim`,
`card_management`, `kyc_update`, `fraud_report`, `complaint`, `ticket_status`, `general_inquiry`,
`human_escalation`.

### Tickets, and what "held" means

Every customer query creates a ticket. The escalation rules do **not** decide whether a ticket
exists — they decide whether the reply is **held for a human**:

- `LOGGED` — answered and auto-sent; the ticket is a record, nobody is following up
- `OPEN` — held for review, or promoted because a later message needed a person
- `CLOSED` — resolved

A held reply appears in the agent console as an editable draft with the hold reason shown.

---

## Services

| Service | Port | Purpose |
|---|---|---|
| `api` | 8888 → 8000 | FastAPI backend + both UIs |
| `neo4j` | 7474 / 7687 | Customer records, tickets, resolution memory |
| `opensearch` | 9200 | Knowledge base vector + lexical index |
| `ollama` | 11434 | Local LLM (classification fallback) |
| `mailpit` | 8025 / 1025 | Local mail catcher for email testing |
| `ngrok` | 4040 | Public tunnel for the WhatsApp webhook |

**Groq** is the cloud LLM used for generation and classification and runs outside Docker.

### Docker volumes

| Volume | Holds | Safe to wipe? |
|---|---|---|
| `cx-data` | SQLite: conversations, tickets, drafts, audit, logins | Yes — destroys logins |
| `neo4j-data` | Customer graph | Yes — triggers reseed on boot |
| `opensearch-data` | Knowledge base index | Yes — needs manual re-index |
| `ollama-data` | Pulled model (GBs) | **Keep** |
| `huggingface-cache` | Embedding model | **Keep** |

---

## Quick start

### Prerequisites

Docker Desktop, a Groq API key, and ~6 GB free disk.

### 1. Create `.env`

```env
APP_ENV=local
LOG_LEVEL=INFO
ADMIN_API_KEY=choose-a-long-random-string
DATABASE_PATH=/app/data/cx_phase1.db

# LLM — Groq (cloud, primary)
GROQ_API_KEY=your-groq-key
GROQ_MODEL=openai/gpt-oss-120b
GROQ_TIMEOUT_SECONDS=60

# LLM — Ollama (local, fallback)
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:0.5b

# Graph
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=choose-a-password

# Knowledge base
OPENSEARCH_URL=http://opensearch:9200
OPENSEARCH_INDEX=cx_knowledge_base
EMBEDDING_BACKEND=sentence_transformers
RAG_TOP_K=4

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your@gmail.com
IMAP_ENABLED=true
IMAP_HOST=imap.gmail.com
IMAP_USERNAME=your@gmail.com
IMAP_PASSWORD=your-app-password

# WhatsApp (Meta Cloud API)
WHATSAPP_ACCESS_TOKEN=your-token
WHATSAPP_PHONE_NUMBER_ID=your-id
WHATSAPP_VERIFY_TOKEN=your-verify-token
WHATSAPP_APP_SECRET=your-app-secret
WHATSAPP_LOCAL_TEST_MODE=true

OUTBOUND_DELIVERY_MODE=log
```

`.env` is gitignored. `WHATSAPP_LOCAL_TEST_MODE=true` affects **inbound only** — outbound always
calls Meta's real API.

### 2. Start

```bash
docker compose up -d
docker compose ps          # all healthy
```

The api container runs database migrations before starting uvicorn, and Neo4j reseeds the demo
customers from `data/bfsi.xlsx` automatically **when the graph is empty** — so wiping the graph
volume is what triggers a reseed.

### 3. Pull the local model (first run only)

```bash
docker compose --profile setup run --rm ollama-pull
```

### 4. Index the knowledge base (not automatic)

```powershell
$H = @{ "x-admin-key" = "<ADMIN_API_KEY>" }
Invoke-RestMethod -Method Post -Headers $H "http://localhost:8888/admin/rag/index?recreate=true"
```

Expect `indexed > 0` and `errors: 0`.

### 5. Open the UI

http://localhost:8888/admin-ui — then sign up on the portal using an email or phone that
**matches a seeded customer**, or identity resolution will reject the signup as unregistered.

---

## Verifying the stack

Seven external dependencies can each break things in ways that look like application bugs.

```powershell
$H = @{ "x-admin-key" = "<ADMIN_API_KEY>" }

Invoke-RestMethod "http://localhost:8888/health"
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/neo4j/status"          # Customer: 5
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/rag/health"
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/orchestration/ai-runtime"
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/email/status"
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/crm/status"
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/llm-observability/summary?days=1"
```

`docs/rules_to_follow/fresh-start-runbook.md` has the full checklist and a verified
full-wipe-and-restart procedure.

---

## The agent console

- **Inbox** — conversations grouped into one thread per matter, across channels
- **Held drafts** — replies awaiting review, with the hold reason and an editable body
- **Customer 360** — the customer's record, grouped into tabs
- **Knowledge graph** — a live force-directed view of the database, and a schema view
- **Workflow** — the running LangGraph pipeline as a diagram
- **Analytics** — volumes, channels, resolution and SLA figures
- **LLM operations** — every model call with tokens, latency and cost
- **Connectors** — configuration status for WhatsApp, email and CRM

> Connector badges report **configured**, not **reachable** — a green badge with an expired
> token is possible.

---

## Testing

```bash
docker compose exec api pytest -q          # inside the container
```

`tests/conftest.py` blocks outbound network calls, so the suite spends no Groq quota and creates
no CRM tickets.

Three things to know:

1. **Python source is baked into the image**, except `apps/admin-ui`, which is bind-mounted.
   A Python change needs `docker compose build api && docker compose up -d api` — a plain
   restart runs the old code. Tests are baked in too.
2. **Do not use the UI while the suite runs.** The Groq guard is process-wide and will silently
   block a live message's model calls.
3. **Never drive the pipeline on a channel that can deliver to a real person.** Use
   `Channel.WEB_CHAT`, whose delivery path returns without sending.

---

## Quota

Groq's free tier is bound by **requests per day**, not tokens. One customer message costs roughly
six model calls, so plan demo runs accordingly. `/admin/llm-observability/events` shows spend as
it accumulates.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| "Invalid user ID or password" after a data wipe | Logins live in `cx-data`; recreate them |
| Replies dump raw records at the customer | Groq quota exhausted — check for 429s |
| A Python fix appears not to work | Stale image — rebuild, don't restart |
| WhatsApp outbound 401 | Expired Meta token; a System User token does not expire |
| ngrok `ERR_NGROK_334` | The shared free-tier domain is held by someone else |
| Empty customer data for a real customer | Identity resolution found no match on email/phone |
| Knowledge base returns nothing | OpenSearch wiped without re-indexing |

---

## Repository layout

```text
apps/
  api/          FastAPI app, routes, dependencies
  admin-ui/     Agent console + customer portal (one SPA)
services/       One package per concern (see the table above)
shared/         Schemas, prompts, utilities
data/           Seed workbook, knowledge base, SQLite
docs/           Design notes, runbooks, the session changes log
tests/          Pytest suite
infra/          Migrations and infrastructure files
```

## Documentation

| Document | What it covers |
|---|---|
| `docs/rules_to_follow/fresh-start-runbook.md` | Full wipe and restart, dependency checklist |
| `docs/rules_to_follow/Sayantini-session-changes-log.md` | Every fix, why it was made, how it was verified |
| `docs/ticket_model_design/ticket-model-redesign.md` | The ticket model and its rationale |
| `docs/production_scope_discussion/` | Production scope and inbound routing |
| `docs/crosssell_upsell_implementation/` | Cross-sell and agent-assist design |
