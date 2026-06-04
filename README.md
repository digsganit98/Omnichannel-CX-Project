# Omnichannel CX Accelerator

A local, Docker-based customer support accelerator for WhatsApp and Email.

It receives customer messages, identifies the customer, keeps conversation history, classifies intent with Ollama, retrieves approved knowledge with semantic search, sends a reply, and creates a support ticket when human follow-up is needed.

The easiest way to test it is the browser UI:

```text
http://localhost:8000/admin-ui
```

## What Is Implemented

### Phase 1: WhatsApp And Email CX Backend

Status: implemented.

Included:

- WhatsApp and Email ingestion
- normalized inbound message schema
- durable SQLite persistence in Docker
- customer identity resolution across phone and email
- conversation history and summaries
- typed intent detection
- RAG answers with citations
- customer-safe knowledge retrieval
- outbound replies through WhatsApp, SMTP, or local test delivery
- ticket fallback and ticket lifecycle management
- audit events and structured logs
- protected admin APIs
- Docker Compose local stack
- automated tests

### Phase 2: LangGraph AI Orchestration Layer

Status: implemented.

LangGraph coordinates four focused agents:

- `intent_detection_agent`: validates Ollama intent output and uses safe fallback rules
- `query_resolution_agent`: retrieves approved knowledge and generates cited answers
- `ticket_management_agent`: applies escalation policy, creates tickets, and syncs optional CRM/Jira records
- `workflow_automation_agent`: sends the final reply and persists audit, context, and evidence

Main code locations:

- LangGraph workflow: `services/orchestration_service/graph.py`
- Agent classes: `services/agent_service/orchestration_agents.py`
- Workflow state: `services/orchestration_service/state.py`
- Admin workflow endpoint: `apps/api/routes/orchestration.py`

## System Flow

```text
WhatsApp or Email message
        |
        v
Channel adapter
        |
        v
Normalized InboundMessage
        |
        v
LangGraph workflow
  1. receive message
  2. resolve customer identity
  3. load conversation context
  4. detect ticket action
  5. classify intent
  6. retrieve approved knowledge
  7. generate answer
  8. decide if ticket is required
  9. create/update/resolve ticket if needed
 10. send outbound reply
 11. persist turns, evidence, and audit events
        |
        v
SQLite | OpenSearch | Ollama | Gmail SMTP or Mailpit | Optional CRM/Jira
```

## Local Services

After the stack is running:

```text
Ticket operations UI: http://localhost:8000/admin-ui
API docs:             http://localhost:8000/docs
API health:           http://localhost:8000/health
Mailpit inbox:        http://localhost:8025
OpenSearch:           http://localhost:9200
Ollama:               http://localhost:11434
```

## Prerequisites

Install Docker Desktop.

You do not need to install SQL locally. SQLite runs inside the Docker API container and persists through the Docker `cx-data` volume.

Python is only needed if you want to run tests outside Docker.

## Quick Start

### 1. Create `.env`

```powershell
Copy-Item .env.example .env
```

Use long random strings for:

```text
ADMIN_API_KEY
EMAIL_WEBHOOK_SECRET
WHATSAPP_TEST_SIGNATURE
WHATSAPP_VERIFY_TOKEN
WHATSAPP_APP_SECRET
```

For local browser testing with Gmail outbound, make sure these are set:

```text
WHATSAPP_LOCAL_TEST_MODE=true
OUTBOUND_DELIVERY_MODE=live
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_FROM_EMAIL=<your-gmail-address>
SMTP_USERNAME=<your-gmail-address>
SMTP_PASSWORD=<gmail-app-password>
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

Gmail sending does not work with a plain API key alone. Use a Gmail App Password for this SMTP path, or add a Gmail OAuth refresh-token flow later.

### 2. Start Docker

```powershell
docker compose up --build -d
```

### 3. Pull the Ollama model

```powershell
docker compose --profile setup run --rm ollama-pull
```

This may take a few minutes the first time.

### 4. Index the knowledge base

Use the `ADMIN_API_KEY` value from `.env`:

```powershell
$headers = @{ "x-admin-key" = "<ADMIN_API_KEY from .env>" }
Invoke-RestMethod -Method Post -Headers $headers "http://localhost:8000/admin/rag/index?recreate=true"
```

Expected result:

```json
{
  "documents_loaded": 1,
  "indexed": 1,
  "errors": 0
}
```

`documents_loaded` and `indexed` may be higher if the PDF is split into multiple indexed chunks.

### 5. Open the UI

Open:

```text
http://localhost:8000/admin-ui
```

Enter your `ADMIN_API_KEY`, then select **Connect**.

## Test In The Browser

The browser UI is the recommended local test surface.

### Test WhatsApp

1. Open `http://localhost:8000/admin-ui`.
2. Enter `ADMIN_API_KEY`.
3. Select **Connect**.
4. Select the **WhatsApp** tab.
5. Enter `WHATSAPP_TEST_SIGNATURE`.
6. Use a Meta-allowed recipient phone number such as:

```text
919999999999
```

7. For local-only testing, keep **Outbound delivery** as `Local mock reply`.
8. For a real WhatsApp response through Meta, select **Real Meta WhatsApp reply**.
9. Submit:

```text
Where is my order delivery?
```

Expected result:

- `intent` is `order_tracking`
- `resolved` is `true`
- citations reference `InboxIQ_BFSI_KB.pdf`
- `outbound_status` is `sent`
- no ticket is created

For real Meta delivery, the phone number must be an allowed test recipient for your Meta WhatsApp sender.

### Test Email

1. Open `http://localhost:8000/admin-ui`.
2. Select the **Email** tab.
3. Enter `EMAIL_WEBHOOK_SECRET`.
4. Use a customer email such as:

```text
customer@example.com
```

5. Submit:

```text
How can I track my order?
```

Expected result:

- the email is ingested through the authenticated email webhook path
- customer identity is resolved by email
- RAG returns cited policy knowledge
- outbound email is sent
- the generated email is sent through Gmail SMTP to the customer email address

### Test Ticket Creation

Submit this from WhatsApp or Email:

```text
This is unacceptable. I want a human representative immediately.
```

Expected result:

- `resolved` is `false`
- a `ticket_id` is returned
- the ticket appears in the support queue
- the audit feed shows classification, ticket creation, and outbound reply events

### Test Ticket Closure From Customer Message

After a ticket exists, send this from the same phone or email:

```text
close the ticket as query is resolved, thanks
```

Expected result:

- `intent` is `ticket_resolution`
- the existing ticket is marked `resolved`
- the workflow trace includes `detect_ticket_action` and `resolve_ticket`
- outbound confirmation is sent

## Knowledge Base And RAG

Customer-facing RAG indexes only the approved PDF knowledge base file from:

```text
data/knowledge_base/InboxIQ_BFSI_KB.pdf
```

Current knowledge file:

- `InboxIQ_BFSI_KB.pdf`

Customer profiles, CRM records, uploaded ticket history, names, cities, phone numbers, emails, and order IDs are intentionally excluded from customer-facing RAG contexts and citations.

If you ever see old customer details in `rag_contexts`, rebuild the index:

```powershell
$headers = @{ "x-admin-key" = "<ADMIN_API_KEY from .env>" }
Invoke-RestMethod -Method Post -Headers $headers "http://localhost:8000/admin/rag/index?recreate=true"
```

## What The UI Shows

The ticket operations UI includes:

- CRM connector status
- ticket queue
- selected ticket detail
- ticket comments
- ticket status update
- manual CRM sync retry
- WhatsApp simulator
- Email simulator
- recent audit events
- raw orchestration response JSON

The simulator shows a progress message and elapsed timer while local Ollama and semantic retrieval are running.

## Verify AI Runtime

Check LangGraph workflow metadata:

```powershell
$headers = @{ "x-admin-key" = "<ADMIN_API_KEY from .env>" }
Invoke-RestMethod -Headers $headers "http://localhost:8000/admin/orchestration/workflow"
```

Expected:

```text
framework: LangGraph
engine: langgraph_state_graph
```

Check Ollama and embeddings:

```powershell
Invoke-RestMethod -Headers $headers "http://localhost:8000/admin/orchestration/ai-runtime"
Invoke-RestMethod -Headers $headers "http://localhost:8000/admin/rag/health"
```

Expected:

- `llm.enabled: true`
- `llm.reachable: true`
- `llm.model_installed: true`
- `embeddings.active_backend: sentence_transformers`

Check WhatsApp Meta configuration:

```powershell
Invoke-RestMethod -Headers $headers "http://localhost:8000/admin/whatsapp/status"
```

Expected for real Meta outbound:

- `access_token_configured: true`
- `phone_number_id_configured: true`
- `meta_outbound_ready: true`

Expected for real Meta webhook setup:

- `verify_token_configured: true`
- `app_secret_configured: true`
- `meta_webhook_ready: true`

Check outbound email configuration:

```powershell
Invoke-RestMethod -Headers $headers "http://localhost:8000/admin/email/status"
```

For Gmail SMTP, expected fields include:

- `host: smtp.gmail.com`
- `port: 587`
- `username_configured: true`
- `password_configured: true`
- `use_tls: true`
- `gmail_ready: true`

## API Testing

Swagger is available at:

```text
http://localhost:8000/docs
```

Useful endpoints:

```text
POST /test/whatsapp/inbound-simulate
POST /test/whatsapp/send
POST /integrations/email/webhook
POST /admin/rag/index?recreate=true
POST /admin/rag/query
GET  /admin/rag/health
GET  /admin/tickets
GET  /admin/audit-events
GET  /admin/orchestration/workflow
GET  /admin/orchestration/ai-runtime
GET  /admin/email/status
POST /admin/email/test-send
GET  /admin/whatsapp/status
GET  /admin/whatsapp/delivery-statuses?provider_message_id=<wamid...>
```

Admin endpoints require:

```text
x-admin-key: <ADMIN_API_KEY>
```

Email webhook testing requires:

```text
x-email-webhook-secret: <EMAIL_WEBHOOK_SECRET>
```

Local WhatsApp testing requires:

```text
x-test-whatsapp-signature: <WHATSAPP_TEST_SIGNATURE>
```

## PowerShell Test Examples

### Email Inbound

```powershell
$headers = @{ "x-email-webhook-secret" = "<EMAIL_WEBHOOK_SECRET from .env>" }
$body = @{
  from_email = "customer@example.com"
  subject = "Order tracking"
  body = "Where is my order?"
  message_id = "email-demo-001"
  metadata = @{ thread_id = "thread-001"; linked_phone = "919999999999" }
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Headers $headers -ContentType "application/json" `
  -Body $body "http://localhost:8000/integrations/email/webhook"
```

### Direct Gmail SMTP Test

```powershell
$headers = @{ "x-admin-key" = "<ADMIN_API_KEY from .env>" }
$body = @{
  to = "<recipient-email>"
  subject = "Omnichannel CX Gmail test"
  body = "This confirms Gmail SMTP outbound is working."
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Headers $headers -ContentType "application/json" `
  -Body $body "http://localhost:8000/admin/email/test-send"
```

### WhatsApp Inbound Simulation

```powershell
$headers = @{ "x-test-whatsapp-signature" = "<WHATSAPP_TEST_SIGNATURE from .env>" }
$body = @{
  from = "919999999999"
  text = "Where is my order delivery?"
  profile_name = "Local WhatsApp Tester"
  message_id = "local-wa-001"
  outbound_provider = "local_mock"
  metadata = @{ linked_email = "customer@example.com" }
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Headers $headers -ContentType "application/json" `
  -Body $body "http://localhost:8000/test/whatsapp/inbound-simulate"
```

Always use a fresh `message_id` for a new test. Reusing the same message ID intentionally returns the deduplicated response.

To simulate inbound locally but send the generated response through the real Meta WhatsApp Cloud API, use:

```powershell
$headers = @{ "x-test-whatsapp-signature" = "<WHATSAPP_TEST_SIGNATURE from .env>" }
$body = @{
  from = "<Meta-allowed-recipient-phone-without-plus>"
  text = "Where is my order delivery?"
  profile_name = "Local WhatsApp Tester"
  message_id = "local-wa-meta-001"
  outbound_provider = "meta"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Headers $headers -ContentType "application/json" `
  -Body $body "http://localhost:8000/test/whatsapp/inbound-simulate"
```

## Real WhatsApp Outbound Test

For a real Meta outbound test, set:

```text
WHATSAPP_ACCESS_TOKEN=<Meta access token>
WHATSAPP_PHONE_NUMBER_ID=<Meta phone number ID>
WHATSAPP_BUSINESS_ACCOUNT_ID=<WhatsApp business account ID, optional for this app>
```

Recreate the API container:

```powershell
docker compose up -d --force-recreate api
```

Then call `POST /test/whatsapp/send` with:

```json
{
  "to": "919999999999",
  "text": "Real outbound Meta WhatsApp test",
  "provider": "meta"
}
```

Use a Meta-verified recipient number in international format without `+`.

## WhatsApp Webhook And Delivery Status

To receive real inbound WhatsApp messages and delivery statuses, expose port `8000` through VS Code Port Forwarding, ngrok, or another approved public tunnel.

Configure Meta with:

```text
https://<public-host>/integrations/whatsapp/webhook
```

In Meta Dashboard, subscribe the webhook to the WhatsApp `messages` field. Meta sends both inbound messages and outbound status callbacks through that same field.

The production webhook validates `x-hub-signature-256` with `WHATSAPP_APP_SECRET`. The verification challenge uses `WHATSAPP_VERIFY_TOKEN`.

After a real WhatsApp send returns a provider message id such as `wamid...`, check delivery status with:

```powershell
$headers = @{ "x-admin-key" = "<ADMIN_API_KEY from .env>" }
Invoke-RestMethod -Headers $headers `
  "http://localhost:8000/admin/whatsapp/delivery-statuses?provider_message_id=<wamid...>"
```

Expected statuses from Meta include:

- `sent`
- `delivered`
- `read`
- `failed`

The app persists each callback in `whatsapp_delivery_statuses`, updates the matching outbound conversation turn, and writes a `whatsapp_delivery_status_received` audit event.

## Optional CRM Or Jira Sync

By default, tickets are stored locally and `crm_sync_status` is `not_configured`.

### Generic CRM

```text
CRM_PROVIDER=generic
CRM_BASE_URL=https://crm.example.com/api
CRM_API_TOKEN=<bearer-token>
```

The accelerator calls:

```text
GET   /customers/resolve?channel=<channel>&identifier=<identifier>
POST  /tickets
POST  /tickets/{external_ticket_id}/comments
PATCH /tickets/{external_ticket_id}
```

### Jira Cloud

```text
CRM_PROVIDER=jira
CRM_BASE_URL=https://your-domain.atlassian.net
CRM_API_TOKEN=<jira-api-token>
CRM_USER_EMAIL=<jira-account-email>
CRM_PROJECT_KEY=<jira-project-key>
CRM_ISSUE_TYPE=Task
```

Ticket creation uses Jira REST API v3. Comments and status transitions are synchronized when a local ticket has an external Jira issue key.

## Run Tests

Inside the Docker image:

```powershell
docker run --rm -v "${PWD}:/app" -w /app omnichannel-cx-project-api:latest python -m pytest -q
```

Or locally, if Python dependencies are installed:

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m compileall -q apps services shared tests
docker compose config --quiet
```

## Troubleshooting

### The UI Looks Unresponsive

Local Ollama can take several seconds on the first request. The simulator shows an elapsed timer. Wait for the result panel to update.

If it still does not respond:

```powershell
docker compose ps
docker compose logs --tail 100 api
```

### Ollama Model Is Missing

Run:

```powershell
docker compose --profile setup run --rm ollama-pull
```

Then verify:

```powershell
$headers = @{ "x-admin-key" = "<ADMIN_API_KEY from .env>" }
Invoke-RestMethod -Headers $headers "http://localhost:8000/admin/orchestration/ai-runtime"
```

### RAG Shows Old Or Wrong Contexts

Rebuild the index:

```powershell
$headers = @{ "x-admin-key" = "<ADMIN_API_KEY from .env>" }
Invoke-RestMethod -Method Post -Headers $headers "http://localhost:8000/admin/rag/index?recreate=true"
```

### Gmail Email Does Not Send

Verify:

```text
OUTBOUND_DELIVERY_MODE=live
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<your-gmail-address>
SMTP_PASSWORD=<gmail-app-password>
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

Then check:

```powershell
$headers = @{ "x-admin-key" = "<ADMIN_API_KEY from .env>" }
Invoke-RestMethod -Headers $headers "http://localhost:8000/admin/email/status"
```

### Docker Compose Network Error

If a one-off setup container has stale networking, run the setup pull again:

```powershell
docker compose --profile setup run --rm ollama-pull
```

## Current Scope

Included:

- WhatsApp
- Email
- durable customer context
- typed intent classification
- LangGraph orchestration
- Ollama-based LLM classification and generation
- sentence-transformer embeddings
- OpenSearch vector retrieval
- cited RAG answers
- ticket fallback
- outbound replies
- audit events
- optional CRM/Jira sync
- browser ticket operations UI

Deferred:

- website chat
- voice
- social channels
- advanced analytics
- agent-assist UI
- PostgreSQL repository
- distributed queue workers
- OAuth identity flows
- CRM-specific inbound webhooks
