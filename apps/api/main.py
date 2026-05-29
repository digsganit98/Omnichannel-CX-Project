from fastapi import FastAPI

from shared.schemas.messages import EmailWebhookPayload, WhatsAppWebhookPayload
from shared.schemas.responses import ChannelResponse
from shared.utils.in_memory_store import store

from .routes.conversations import router as conversations_router
from .routes.integrations import router as integrations_router
from .routes.synthetic import router as synthetic_router
from .routes.tickets import router as tickets_router
from .routes.webhooks import handle_email_message, handle_whatsapp_message

app = FastAPI(
    title="GenAI Omnichannel CX Accelerator",
    description="Email and WhatsApp query resolution with unified customer context.",
    version="0.1.0",
)

app.include_router(conversations_router)
app.include_router(tickets_router)
app.include_router(synthetic_router)
app.include_router(integrations_router)


@app.get("/")
def root() -> dict:
    return {
        "name": "GenAI Omnichannel CX Accelerator",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "apps": {
            "agent_studio": "http://localhost:8501",
            "analytics": "http://localhost:8502",
        },
        "api_routes": {
            "whatsapp_demo": "POST /webhooks/whatsapp",
            "email_demo": "POST /webhooks/email",
            "uploaded_records": "GET /synthetic/uploaded-records",
            "uploaded_summary": "GET /synthetic/uploaded-summary",
            "whatsapp_cloud": "GET/POST /integrations/whatsapp/webhook",
            "outlook": "POST /integrations/outlook/pull or GET/POST /integrations/outlook/webhook",
            "gmail": "POST /integrations/gmail/pull or POST /integrations/gmail/webhook",
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "omnichannel-cx-api"}


@app.post("/webhooks/whatsapp", response_model=ChannelResponse)
def whatsapp_webhook(payload: WhatsAppWebhookPayload) -> ChannelResponse:
    response = handle_whatsapp_message(payload)
    store.record_metric("whatsapp_messages")
    return response


@app.post("/webhooks/email", response_model=ChannelResponse)
def email_webhook(payload: EmailWebhookPayload) -> ChannelResponse:
    response = handle_email_message(payload)
    store.record_metric("email_messages")
    return response
