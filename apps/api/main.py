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
