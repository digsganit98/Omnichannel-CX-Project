# Omnichannel CX Accelerator

Production-oriented WhatsApp and email customer support backend with durable conversations, typed intent classification, cited RAG answers, ticket fallback, outbound replies, audit events, CRM orchestration, a ticket-operations UI, and local Docker deployment.

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
- runs locally with Docker Compose, SQLite, OpenSearch, Mailpit, Ollama generation, and sentence-transformer embeddings
- includes automated tests for the main workflow, security, deduplication, citations, delivery, and restart persistence

### Later Phases

Planned additions may include website chat, voice, social channels, advanced analytics, agent-assist UI, PostgreSQL for horizontal scaling, durable queue workers, CRM-specific inbound webhooks, and production identity integrations.

### Ticket Management And CRM Integration

Status: implemented.

The accelerator now includes a durable ticket-management and optional CRM synchronization layer adapted from the supplied InboxIQ and Ticketmate prototypes. The implementation keeps the useful workflow patterns while fitting the existing Phase 1 API, persistence, and audit architecture.

### Phase 2: LangGraph AI Orchestration Layer

Status: implemented.

The post-Phase-1 AI orchestration layer uses LangGraph `StateGraph` to coordinate four focused agents:

- `intent_detection_agent`: validates Ollama classification output and falls back to deterministic rules
- `query_resolution_agent`: retrieves relevant knowledge and generates cited answers
- `ticket_management_agent`: applies escalation policy, creates durable tickets, and synchronizes optional CRM or Jira records
- `workflow_automation_agent`: loads context, composes the final action, sends the channel reply, and persists results

LangGraph executes the named workflow nodes and conditionally routes each request after resolution analysis. Requests that need human review pass through durable ticket creation and optional CRM synchronization. Resolved requests bypass ticket creation and continue directly to outbound reply delivery.

The ticket-management foundation:

- creates local tickets first so customer support continues even when an external CRM is unavailable
- assigns teams, priorities, approval state, escalation reasons, and SLA deadlines
- stores external CRM or Jira ticket IDs, links, synchronization status, and errors
- enriches customer profile metadata through an optional CRM lookup
- synchronizes ticket creation to a generic CRM REST API or Jira Cloud
- supports ticket comments, status changes, manual resynchronization, and lifecycle event history
- records CRM synchronization and ticket-management actions in the global audit feed
- uses Jira-compatible Atlassian Document Format descriptions when `CRM_PROVIDER=jira`
- includes a browser-based ticket-operations UI for queue review, ticket updates, CRM sync, audit review, and local WhatsApp flow simulation

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
                      | Optional CRM REST API or Jira Cloud
```

The default repository is durable SQLite behind `CXRepository`. Tests use the same implementation with `:memory:`. For a multi-instance deployment, implement the same interface with PostgreSQL and use a shared queue for delivery retries.

The default container installs `sentence-transformers` and uses `all-MiniLM-L6-v2` semantic embeddings. Set `EMBEDDING_BACKEND=hashing` only for constrained smoke tests. Intent classification and cited query resolution use Ollama by default; deterministic rules and grounded retrieval text remain available as failure fallbacks. Ticket escalation and workflow routing intentionally remain deterministic business policy.

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
docker compose --profile setup run --rm ollama-pull
```

Open the local services:

```text
API documentation: http://localhost:8000/docs
API health check:  http://localhost:8000/health
Ticket operations:  http://localhost:8000/admin-ui
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

## Local WhatsApp Test Mode

Use local WhatsApp test mode when Meta cannot reach your development machine. It exercises the same adapter, identity resolution, persistence, classification, RAG, ticket fallback, outbound delivery, structured logging, and audit workflow without calling Meta.

Local WhatsApp simulation is disabled by default. Enable it only in your local `.env`:

```text
WHATSAPP_LOCAL_TEST_MODE=true
WHATSAPP_TEST_SIGNATURE=<long-random-local-test-value>
```

Recreate the API container after changing `.env`:

```powershell
docker compose up -d --force-recreate api
```

In Swagger at `http://localhost:8000/docs`, expand `POST /test/whatsapp/inbound-simulate`, enter your local `WHATSAPP_TEST_SIGNATURE` value in `x-test-whatsapp-signature`, and submit:

```json
{
  "from": "919999999999",
  "text": "Where is my order delivery?",
  "profile_name": "Local WhatsApp Tester",
  "message_id": "local-wa-001",
  "metadata": {
    "linked_email": "e2e-customer@example.com"
  }
}
```

The response should include a canonical `customer_id`, `conversation_id`, `intent`, citations, and `outbound_status: sent`.

To simulate a direct outbound provider send, use `POST /test/whatsapp/send` with the same signature header:

```json
{
  "to": "919999999999",
  "text": "Local WhatsApp outbound test",
  "provider": "local_mock"
}
```

To send a real outbound WhatsApp message through Meta without exposing a webhook, configure:

```text
WHATSAPP_ACCESS_TOKEN=<Meta temporary or permanent access token>
WHATSAPP_PHONE_NUMBER_ID=<Meta test phone number ID>
```

Recreate the API container and call `POST /test/whatsapp/send` with:

```json
{
  "to": "919999999999",
  "text": "Real outbound Meta WhatsApp test",
  "provider": "meta"
}
```

Use your verified recipient phone number in international format without `+`. Meta must allow the recipient for the configured test sender.

Inspect the full workflow using:

```text
GET /admin/audit-events?correlation_id=<response-correlation-id>
```

Use your `.env` `ADMIN_API_KEY` value as the `x-admin-key` header. Container logs also show the local inbound and outbound events:

```powershell
docker compose logs --tail 100 api
```

The local endpoints return `404` unless `WHATSAPP_LOCAL_TEST_MODE=true`. The production Meta webhook remains unchanged.

## Phase 1 Test Plan

### Today

1. Simulated WhatsApp webhook test:
   Use `POST /test/whatsapp/inbound-simulate`. This verifies the complete backend workflow and mock outbound reply without a public webhook URL.

2. Real WhatsApp outbound test using Meta API:
   Configure `WHATSAPP_ACCESS_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID`, then use `POST /test/whatsapp/send` with `"provider": "meta"`. This sends a real WhatsApp message to your verified recipient number.

3. Email inbound and outbound test:
   Use `POST /integrations/email/webhook` to simulate inbound email. Configure SMTP settings for outbound delivery. For Docker Mailpit testing:

```text
OUTBOUND_DELIVERY_MODE=live
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_FROM_EMAIL=support@example.com
SMTP_USE_TLS=false
```

For a real SMTP test account, use settings supplied by the email provider. A typical STARTTLS configuration is:

```text
OUTBOUND_DELIVERY_MODE=live
SMTP_HOST=<smtp-provider-host>
SMTP_PORT=587
SMTP_FROM_EMAIL=<test-account-email>
SMTP_USERNAME=<test-account-email>
SMTP_PASSWORD=<test-account-app-password>
SMTP_USE_TLS=true
```

Use an app password or dedicated SMTP credential where supported. Do not commit credentials to Git.

### Later

Expose port `8000` through VS Code Port Forwarding or an IT-installed ngrok tunnel, then configure Meta to send production-shaped inbound webhook traffic to:

```text
https://<public-host>/integrations/whatsapp/webhook
```

The real Meta route validates `x-hub-signature-256` with `WHATSAPP_APP_SECRET`.

## Admin APIs

All internal APIs require `x-admin-key`:

```text
POST /admin/rag/index?recreate=true
POST /admin/rag/query
GET  /admin/rag/health
GET  /admin/tickets
GET  /admin/tickets/{ticket_id}
GET  /admin/tickets/{ticket_id}/events
POST /admin/tickets/{ticket_id}/sync
POST /admin/tickets/{ticket_id}/comments
PATCH /admin/tickets/{ticket_id}/status
GET  /admin/conversations
GET  /admin/audit-events
GET  /admin/crm/status
GET  /admin/orchestration/workflow
```

Customer-facing RAG indexes only approved files under `data/knowledge_base/*.md`. Customer profiles, CRM records, and historical ticket exports are intentionally excluded from answer retrieval and citations. After upgrading an existing checkout, rebuild the vector index once to remove older ticket-history vectors:

```powershell
$headers = @{ "x-admin-key" = "<ADMIN_API_KEY from .env>" }
Invoke-RestMethod -Method Post -Headers $headers "http://localhost:8000/admin/rag/index?recreate=true"
```

## CRM And Ticket-System Integration

CRM synchronization is optional. With the default configuration, tickets remain durable local records and show `crm_sync_status: not_configured`.

### Generic CRM REST API

Set:

```text
CRM_PROVIDER=generic
CRM_BASE_URL=https://crm.example.com/api
CRM_API_TOKEN=<bearer-token>
```

The accelerator uses:

```text
GET   /customers/resolve?channel=<channel>&identifier=<identifier>
POST  /tickets
POST  /tickets/{external_ticket_id}/comments
PATCH /tickets/{external_ticket_id}
```

### Jira Cloud

Set:

```text
CRM_PROVIDER=jira
CRM_BASE_URL=https://your-domain.atlassian.net
CRM_API_TOKEN=<jira-api-token>
CRM_USER_EMAIL=<jira-account-email>
CRM_PROJECT_KEY=<jira-project-key>
CRM_ISSUE_TYPE=Task
```

Ticket creation uses Jira REST API v3. Comments and status transitions are synchronized when a local ticket has an external Jira issue key.

### Manage Tickets In Swagger

Open `http://localhost:8000/docs`, provide your `.env` `ADMIN_API_KEY` as `x-admin-key`, then use:

```text
GET   /admin/tickets
GET   /admin/tickets/{ticket_id}/events
POST  /admin/tickets/{ticket_id}/sync
POST  /admin/tickets/{ticket_id}/comments
PATCH /admin/tickets/{ticket_id}/status
GET   /admin/crm/status
```

### Manage Tickets In The Browser UI

Open `http://localhost:8000/admin-ui`, enter the `ADMIN_API_KEY` from your local `.env`, and select **Connect**. The ticket-operations page shows CRM configuration status, the durable support queue, ticket details, lifecycle events, and recent global audit events.

Select a ticket to update its status, add an internal or CRM-synchronized comment, or manually retry CRM synchronization. The page also includes WhatsApp and Email inbound simulation tabs. For WhatsApp, enter the `WHATSAPP_TEST_SIGNATURE` from `.env`; local test mode must be enabled with `WHATSAPP_LOCAL_TEST_MODE=true`. For Email, enter the `EMAIL_WEBHOOK_SECRET` from `.env`. Email submissions use the authenticated `POST /integrations/email/webhook` ingestion path and send outbound replies through the configured log or SMTP delivery mode.

The simulator immediately shows a processing state and elapsed timer while the orchestration request is running, then displays a compact outcome summary above the raw JSON. To test customer-driven ticket closure, first simulate a complaint or human-escalation message, then send `close the ticket as query is resolved, thanks` from the same phone number. The workflow marks the active ticket as resolved, sends a confirmation reply, and records `detect_ticket_action` and `resolve_ticket` in `workflow_trace`.

The UI stores secrets only in browser `sessionStorage`. For a production deployment, place this internal operations page behind your organization SSO or authenticated reverse proxy.

### Inspect The AI Orchestration Workflow

Use the protected workflow-definition route to inspect the configured agents and execution order:

```powershell
$headers = @{ "x-admin-key" = "<ADMIN_API_KEY from .env>" }
Invoke-RestMethod -Headers $headers "http://localhost:8000/admin/orchestration/workflow"
```

Every processed message also returns `workflow_trace` and stores `workflow_step_completed` audit events. The workflow-definition response reports `framework: LangGraph`, the configured agents, and graph edges. This exposes the exact agent and workflow step responsible for each action.

Verify the configured AI runtime and Ollama model availability:

```powershell
Invoke-RestMethod -Headers $headers "http://localhost:8000/admin/orchestration/ai-runtime"
Invoke-RestMethod -Headers $headers "http://localhost:8000/admin/rag/health"
```

The first response should show `llm.enabled: true`, `llm.reachable: true`, and `llm.model_installed: true`. The RAG health response should show `embeddings.active_backend: sentence_transformers`. The first semantic model load downloads and caches `all-MiniLM-L6-v2`.

## Tests

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m compileall -q apps services shared tests
docker compose config --quiet
```

The tests cover WhatsApp and email ingestion paths, duplicate handling, canonical identity linking, multi-turn persistence, intent classification, citations, ticket fallback, outbound sends, signature validation, restart persistence, CRM profile enrichment, ticket synchronization, comments, and status changes.

## Phase 1 Scope

Included: WhatsApp, email, durable customer context, typed intent classification, cited RAG, ticket fallback, outbound delivery, structured logs, persisted audit events, basic ticket management, optional CRM/Jira orchestration, and a ticket-operations UI.

Deferred: website chat, voice, social channels, advanced analytics, customer-service agent-assist UI, PostgreSQL repository, distributed queue workers, OAuth consent flows, CRM-specific inbound webhooks, and scheduled postmortem reporting.
