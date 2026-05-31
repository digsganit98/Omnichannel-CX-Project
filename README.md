# Omnichannel CX Accelerator: Phase 1

Production-oriented WhatsApp and email customer support backend with durable conversations, typed intent classification, cited RAG answers, ticket fallback, outbound replies, audit events, and local Docker deployment.

## Project Progress

This README is the living implementation guide for the accelerator. Update this section as each phase is completed.

### Phase 1: WhatsApp And Email CX Backend

Status: implemented.

Phase 1 delivers a production-oriented customer support backend focused on WhatsApp and email. The system:

- accepts authenticated WhatsApp Cloud and email webhook messages
- normalizes both channels into one common inbound message schema
- deduplicates repeated provider messages using external message IDs
- resolves customers across email addresses and WhatsApp phone numbers
- persists customers, channel identities, conversations, turns, tickets, audit events, and retrieval evidence
- classifies typed intents including order tracking, refunds, returns, product questions, billing issues, technical support, complaints, general inquiries, and human escalation
- retrieves relevant knowledge from OpenSearch and returns answers with citations
- creates support tickets when confidence is low, urgency is high, a human is requested, or manual review is required
- sends replies through WhatsApp Cloud or SMTP email
- stores structured audit events for workflow decisions and outbound delivery
- preserves conversation context after API container restarts
- protects internal admin APIs and validates inbound webhook secrets
- runs locally with Docker Compose, SQLite, OpenSearch, Mailpit, and optional Ollama generation
- includes automated tests for the main workflow, security, deduplication, citations, delivery, and restart persistence

### Later Phases

Planned additions may include website chat, voice, social channels, advanced analytics, agent-assist UI, PostgreSQL for horizontal scaling, durable queue workers, external ticket-system synchronization, and production identity integrations.

## Architecture

```text
WhatsApp Cloud webhook / authenticated email webhook
        |
        v
Channel adapter -> normalized InboundMessage
        |
        v
Explicit orchestration workflow
  1. reserve provider message ID for deduplication
  2. resolve canonical customer and channel identity
  3. persist inbound turn and load recent context
  4. classify typed intent with Ollama or validated rules
  5. retrieve versioned KB chunks from OpenSearch or local fallback
  6. answer with citations or create/update a ticket
  7. send reply through WhatsApp Cloud or SMTP email
  8. persist outbound turn, retrieval evidence, summary, and audit events
        |
        v
SQLite durable volume | OpenSearch | Ollama | Mailpit for local SMTP
```

The default repository is durable SQLite behind `CXRepository`. Tests use the same implementation with `:memory:`. For a multi-instance deployment, implement the same interface with PostgreSQL and use a shared queue for delivery retries.

The container includes semantic embedding support through `sentence-transformers`. Set `EMBEDDING_BACKEND=sentence_transformers` to enable it. The deterministic hashing backend remains available for lightweight runs.

## Configure

```powershell
Copy-Item .env.example .env
```

Set strong values for:

```text
ADMIN_API_KEY
EMAIL_WEBHOOK_SECRET
WHATSAPP_VERIFY_TOKEN
WHATSAPP_APP_SECRET
```

For live WhatsApp delivery, also set `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, and `OUTBOUND_DELIVERY_MODE=live`.

For local email delivery through Mailpit, set `OUTBOUND_DELIVERY_MODE=live`. Open `http://localhost:8025` to inspect sent emails.

## Run Locally

```powershell
docker compose up --build -d
docker compose --profile setup up ollama-pull
```

Open the local services:

```text
API documentation: http://localhost:8000/docs
API health check:  http://localhost:8000/health
Mailpit inbox:     http://localhost:8025
```

The API runs migrations automatically. To apply them manually outside Docker:

```powershell
python -m services.persistence_service.migrate
```

Index the knowledge base:

```powershell
$headers = @{ "x-admin-key" = "replace-with-a-long-random-value" }
Invoke-RestMethod -Method Post -Headers $headers "http://localhost:8000/admin/rag/index?recreate=true"
```

## Trigger Email Flow

```powershell
$headers = @{ "x-email-webhook-secret" = "replace-with-a-long-random-value" }
$body = @{
  from_email = "customer@example.com"
  subject = "Delivery update"
  body = "Where is my order?"
  message_id = "email-demo-001"
  metadata = @{ linked_phone = "919999999999"; thread_id = "thread-001" }
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Headers $headers -ContentType "application/json" `
  -Body $body http://localhost:8000/integrations/email/webhook
```

Expected output includes a canonical `customer_id`, `conversation_id`, typed `intent`, citations, and `outbound_status`.

## Browser Walkthrough

Use FastAPI Swagger to test the complete local email workflow without installing a separate SQL server.

1. Open `http://localhost:8000/docs`.
2. Expand `POST /admin/rag/index`, click **Try it out**, set `recreate=true`, enter your `.env` `ADMIN_API_KEY` value in `x-admin-key`, and click **Execute**.
3. Expand `POST /integrations/email/webhook`, click **Try it out**, and enter your `.env` `EMAIL_WEBHOOK_SECRET` value in `x-email-webhook-secret`.
4. Submit an order-tracking payload:

```json
{
  "from_email": "e2e-customer@example.com",
  "subject": "Order status",
  "body": "Where is my order delivery?",
  "message_id": "browser-email-001",
  "metadata": {
    "thread_id": "browser-thread-001",
    "linked_phone": "919999999999"
  }
}
```

5. Confirm the response includes `intent: order_tracking`, `resolved: true`, citations, and `outbound_status: sent`.
6. Open `http://localhost:8025` and confirm that Mailpit received the generated reply.
7. Submit a complaint using a fresh `message_id`:

```json
{
  "from_email": "e2e-customer@example.com",
  "subject": "Complaint",
  "body": "This is unacceptable. I want a human representative.",
  "message_id": "browser-email-002",
  "metadata": {
    "thread_id": "browser-thread-001"
  }
}
```

8. Confirm the complaint response includes `resolved: false`, a `ticket_id`, and `outbound_status: sent`.
9. Use the protected admin routes in Swagger to inspect tickets, conversations, and audit events.

Always use a fresh `message_id` when testing a new message. Duplicate IDs are intentionally deduplicated.

## Trigger WhatsApp Flow

Meta sends `POST /integrations/whatsapp/webhook`. The route verifies `x-hub-signature-256` with `WHATSAPP_APP_SECRET`, normalizes supported WhatsApp text interactions, deduplicates `messages[].id`, and sends the final reply through WhatsApp Cloud.

Webhook verification uses:

```text
GET /integrations/whatsapp/webhook
```

## Admin APIs

All internal APIs require `x-admin-key`:

```text
POST /admin/rag/index?recreate=true
POST /admin/rag/query
GET  /admin/rag/health
GET  /admin/tickets
GET  /admin/conversations
GET  /admin/audit-events
```

## Tests

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m compileall -q apps services shared tests
docker compose config --quiet
```

The tests cover WhatsApp and email ingestion paths, duplicate handling, canonical identity linking, multi-turn persistence, intent classification, citations, ticket fallback, outbound sends, signature validation, and restart persistence.

## Phase 1 Scope

Included: WhatsApp, email, durable customer context, typed intent classification, cited RAG, ticket fallback, outbound delivery, structured logs, and persisted audit events.

Deferred: website chat, voice, social channels, advanced analytics, agent-assist UI, PostgreSQL repository, distributed queue workers, OAuth consent flows, and external ticket-system synchronization.
