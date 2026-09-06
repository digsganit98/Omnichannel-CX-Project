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

**The knowledge base lives in the same graph.** Process questions ("how do I file a claim?") are
answered from the KB document, chunked and embedded as `(:KBChunk)` nodes, and both sources can
reach the model on the same message. The chunks are not merely stored beside the customer records —
each is linked by `[:ABOUT]` to the `(:Product)` it describes, so retrieval can follow a customer's
own holdings to the text about them. Set `RAG_BACKEND=opensearch` to put the KB back in OpenSearch;
retrieval measured identical either way, and Neo4j is the default because it drops a second
datastore and can hold those links.

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
| `neo4j` | 7474 / 7687 | Customer records, tickets, resolution memory, KB chunks |
| `opensearch` | 9200 | KB index only when `RAG_BACKEND=opensearch` (not the default) |
| `ollama` | 11434 | Local LLM (classification fallback) |
| `mailpit` | 8025 / 1025 | Local mail catcher for email testing |
| `ngrok` | 4040 | Public tunnel for the WhatsApp webhook |

**Groq** is the cloud LLM used for generation and classification and runs outside Docker.

### Docker volumes

| Volume | Holds | Safe to wipe? |
|---|---|---|
| `cx-data` | SQLite: conversations, tickets, drafts, audit, logins | Yes — destroys logins |
| `neo4j-data` | Customer graph + KB chunks | Yes — reseeds on boot, but the KB needs a manual re-index |
| `opensearch-data` | KB index, only on the OpenSearch backend | Yes — needs manual re-index |
| `ollama-data` | Pulled model (GBs) | **Keep** |
| `huggingface-cache` | Embedding model | **Keep** |

---

## Running it locally, start to finish

Nine steps from a clone to a working app. Run them in order.

### 0. Prerequisites

- **Docker Desktop**, running
- A **Groq API key** (free tier) - https://console.groq.com
- **~8 GB RAM free**, **~20 GB disk**

Email and WhatsApp credentials are optional. Skip them and web chat still works end to end.

### 1. Clone and create `.env`

```bash
git clone <repo-url>
cd Omnichannel-CX-Project
cp .env.example .env
```

Edit `.env` and set these five:

| Key | Value |
|---|---|
| `GROQ_API_KEY` | your Groq key - no key, no AI replies |
| `GROQ_MODEL` | `openai/gpt-oss-120b` |
| `ADMIN_API_KEY` | any long random string you invent |
| `NEO4J_PASSWORD` | any password you invent |
| `JWT_SECRET` | any random string, 32+ characters |

Leave everything else at its default.

### 2. Start the stack

```bash
docker compose up -d
docker compose ps
```

Wait until `api`, `neo4j` and `opensearch` say **healthy**. **First boot takes 10-20 minutes**
- images download and the embedding model is fetched.

Migrations run automatically, and the 5 demo customers are seeded into an empty graph.

### 3. Pull the local model

```bash
docker compose --profile setup run --rm ollama-pull
```

### 4. Check the customers seeded

```powershell
$H = @{ "x-admin-key" = "<your ADMIN_API_KEY>" }
Invoke-RestMethod -Headers $H "http://localhost:8888/admin/neo4j/status"
```

**Expect `Customer: 5`.** If it is 0, stop here - everything downstream would answer from an
empty database. `POST /admin/neo4j/load` seeds it by hand.

### 5. Index the knowledge base

```powershell
Invoke-RestMethod -Method Post -Headers $H "http://localhost:8888/admin/rag/index?recreate=true"
Invoke-RestMethod -Method Post -Headers $H "http://localhost:8888/admin/rag/link-kb-graph"
```

**Expect `indexed` above 0 and `errors: 0`** from the first call, and `linked_chunks: 11` /
`unlinked_chunks: 3` from the second. Neither is automatic, and without the first, questions
about processes ("how do I file a claim?") come back empty.

The second call is the Phase 2 step: it links each chunk to the `(:Product)` it describes, so
retrieval can follow a customer's own holdings. It only applies on the Neo4j backend and returns
400 on OpenSearch. **Three chunks stay unlinked on purpose** — Demat, SIP and ELSS describe
investment products this catalogue does not sell; they are still retrievable by vector search.

### 6. Check Groq has quota

```bash
docker exec omnichannel-cx-project-api-1 python -c "import os; from groq import Groq; print(Groq(api_key=os.getenv('GROQ_API_KEY')).chat.completions.create(model=os.getenv('GROQ_MODEL'),messages=[{'role':'user','content':'hi'}],max_tokens=1).choices[0].message.content is not None)"
```

**Expect `True`.** A 429 means the daily budget is spent - worth knowing now, because the app
does not fail loudly when it runs out. Replies just come back empty.

### 7. Create an admin account

Open **http://localhost:8888/admin-ui** → **Admin** tab → **Sign Up**.

No admin account is seeded, so the first sign-in has to be a sign-up.

### 8. Create a customer account

**Customer Login** tab → **Sign Up**, using an email or phone from this table:

| Customer | Email | Phone |
|---|---|---|
| Sayantini Sarkar | sayantini.s.55@gmail.com | 917890864700 |
| Sireesha | s.sireesha28092004@gmail.com | 9398314492 |
| Digvijay Yadav | digvijayyadav48@gmail.com | 917700920746 |
| Hirithi Nandha | hirithi.nandha@gmail.com | 9150697784 |
| Fathima Devasahayam | fathimawork511@gmail.com | 7538870992 |

Any other email or phone is rejected as an unregistered customer.

### 9. Send a message

In the portal, ask *"What is my credit card limit?"* The reply appears in the portal, and the
whole exchange appears in the agent console.

---

## Starting and stopping

```bash
docker compose up -d      # start
docker compose down       # stop - keeps all data
```

After `down`, the next `up -d` comes back with the same conversations, logins and knowledge
index. Nothing to redo.

```bash
docker compose down -v    # stop and DELETE all data - irreversible
```

`-v` deletes conversations, tickets, **both logins**, the customer graph, the knowledge index
and the downloaded models. After it, **redo steps 2 and 4-8**.

---

## Gotchas

**A Python change needs a rebuild, not a restart.** Only `apps/admin-ui` is bind-mounted;
everything else is baked into the image, so a restart runs the old code:

```bash
docker compose build api && docker compose up -d api
```

**UI changes need a hard refresh** (Ctrl+Shift+R). If a change still does not show, bump the
`?v=` on the `style.css` / `app.js` tags in `index.html` - both are cache-busted by query
string.

**ngrok may fail with `ERR_NGROK_334`.** That means a teammate holds the shared free-tier
domain. Ignore it - it only affects real WhatsApp inbound, and nothing else depends on it.

**On Windows, check your shell is not shadowing `.env`.** `docker compose` ranks shell
environment above the file:

```powershell
echo $env:WHATSAPP_ACCESS_TOKEN   # should print nothing
echo $env:NGROK_DOMAIN            # should print nothing
```

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
| Knowledge base returns nothing | Store wiped without re-indexing — `POST /admin/rag/index?recreate=true`, then `/admin/rag/link-kb-graph` on Neo4j |
| `index_create_block_exception` on the OpenSearch backend | The host disk is over 90% full. OpenSearch blocks **all** index creation above that watermark and re-applies the block every ~90s, so clearing the setting does not hold. Free disk, or use the default Neo4j backend, which has no such gate. |
| Python change did nothing | Only `apps/admin-ui` is bind-mounted. `docker compose build api`, not `restart`. |
| `.env` change did nothing | `docker compose restart` reuses the old environment. `docker compose up -d api` recreates and re-reads it. |

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
scripts/        Operational checks that need a live stack (not pytest)
infra/          Migrations and infrastructure files
```

`scripts/compare_rag_backends.py` probes both KB backends over the same questions and prints
which chunk each returned, at what rank. Run it inside the container — it refuses to run where
sentence-transformers has fallen back to hashing embeddings, because a comparison on those
vectors says nothing about either backend. `scripts/verify_kb_graph_links.py` checks the Phase 2
edges and that every customer can reach the KB through their own holdings. Neither calls an LLM.

## Documentation

| Document | What it covers |
|---|---|
| `docs/rules_to_follow/fresh-start-runbook.md` | Full wipe and restart, dependency checklist |
| `docs/rules_to_follow/Sayantini-session-changes-log.md` | Every fix, why it was made, how it was verified |
| `docs/ticket_model_design/ticket-model-redesign.md` | The ticket model and its rationale |
| `docs/production_scope_discussion/` | Production scope and inbound routing |
| `docs/crosssell_upsell_implementation/` | Cross-sell and agent-assist design |
