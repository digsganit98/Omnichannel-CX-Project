# GenAI Omnichannel CX Accelerator

A modular starter repository for a GenAI-powered omnichannel customer support accelerator. It focuses on resolving customer queries from email and WhatsApp while preserving one customer context across channels.

The design follows the proposal in `GenAI_Omnichannel_CX_Accelerator.docx`:

- unify interactions across channels
- normalize messages through channel adapters
- classify intent, sentiment, and urgency
- answer common questions from a knowledge base
- create and track tickets when automation cannot resolve the query
- expose agent assist and analytics foundations

## Quick Start

Use Python 3.11 or 3.12 for the local environment. Python 3.14 can force packages such as `pydantic-core` to compile native Rust/C++ extensions on Windows, which requires Visual Studio Build Tools.

```powershell
cd genai-cx-accelerator
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
uvicorn apps.api.main:app --reload
```

If `py -3.12` is not available, install Python 3.12 from python.org, then recreate the virtual environment:

```powershell
Remove-Item -Recurse -Force .venv
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

API docs will be available at `http://127.0.0.1:8000/docs`.

Optional apps:

```powershell
streamlit run apps/agent-studio/streamlit_app.py
streamlit run apps/analytics/dashboard.py
```

## Main Flow

1. Email or WhatsApp webhook receives a raw message.
2. Channel adapter converts it into a common `InboundMessage`.
3. Conversation manager loads the unified customer context.
4. Orchestrator runs intent, sentiment, urgency, retrieval, and routing.
5. If a confident answer is found, the API returns a response.
6. If confidence is low or urgency is high, a ticket is created.
7. Analytics records message, resolution, channel, ticket, and escalation metrics.

## Example Requests

### WhatsApp

```bash
curl -X POST http://127.0.0.1:8000/webhooks/whatsapp \
  -H "Content-Type: application/json" \
  -d "{\"from\":\"919999999999\",\"text\":\"Where is my order?\",\"profile_name\":\"Asha\"}"
```

## Synthetic E-commerce Data

Generate consolidated omnichannel records from sample WhatsApp and Email messages:

```powershell
python infra\scripts\consolidate_synthetic_tickets.py
```

The script reads `data/synthetic/ecommerce_channel_messages.json` and writes:

```text
data/exports/consolidated_omnichannel_records.json
```

The consolidated output follows `shared/schemas/omnichannel_response_schema.json` and includes customer details, channel metadata, parsed entities, intent, sentiment, urgency, retrieval confidence, resolution status, ticket details, and agent-assist fields.

To use the uploaded Excel workbook as the retrieval/ingestion example:

```powershell
python infra\scripts\import_uploaded_ecommerce_tickets.py
```

This parses `data/uploaded_docs/ecommerce_tickets_synthetic (1).xlsx`, filters Email and WhatsApp tickets, preserves the workbook-style `Customer`, `Account`, and `Ticket` sections, and appends accelerator fields under `AI_Enrichment`. It writes:

```text
data/exports/uploaded_ecommerce_omnichannel_records.json
```

When the API is running, inspect the generated records at:

```text
GET /synthetic/records
GET /synthetic/summary
GET /synthetic/uploaded-records
GET /synthetic/uploaded-summary
```

## Real Connectors

The API includes optional connector endpoints for production ingestion:

```text
GET  /integrations/whatsapp/webhook
POST /integrations/whatsapp/webhook
POST /integrations/outlook/pull
GET  /integrations/outlook/webhook
POST /integrations/outlook/webhook
POST /integrations/gmail/pull
POST /integrations/gmail/webhook
```

- WhatsApp uses Meta WhatsApp Cloud webhook payloads and normalizes incoming `messages[]`.
- Outlook uses Microsoft Graph `/me/messages`.
- Gmail uses Gmail API `users.messages.list` and `users.messages.get?format=raw`.

Set these environment variables before using live connectors:

```text
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
OUTLOOK_ACCESS_TOKEN=
GMAIL_ACCESS_TOKEN=
```

The Outlook and Gmail routes expect OAuth access tokens issued outside this starter app. In production, add an OAuth consent flow, token refresh storage, and webhook subscription renewal jobs.

### Email

```bash
curl -X POST http://127.0.0.1:8000/webhooks/email \
  -H "Content-Type: application/json" \
  -d "{\"from_email\":\"customer@example.com\",\"subject\":\"Refund issue\",\"body\":\"I want a refund for my last order\"}"
```

## Repository Layout

The repository mirrors the requested accelerator structure and keeps service boundaries explicit. Directories use the proposal naming convention, while Python packages under `shared` provide common schemas and storage used by the runnable demo.

## Notes

This is a local-first accelerator scaffold. The default stores are in-memory so the flow is easy to run during an ideathon demo. Production deployments should replace them with durable stores, authenticated webhooks, vector databases, and real integrations such as WhatsApp Cloud API, SMTP/Graph API, CRM, Jira, or ServiceNow.
