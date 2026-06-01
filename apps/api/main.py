import logging
import os
import time

from fastapi import FastAPI, Header

from apps.api.dependencies.security import validate_email_secret
from shared.logging.structured import configure_structured_logging
from shared.schemas.messages import EmailWebhookPayload
from shared.schemas.responses import ChannelResponse

from .routes.audit import router as audit_router
from .routes.conversations import router as conversations_router
from .routes.integrations import router as integrations_router
from .routes.rag import router as rag_router
from .routes.tickets import router as tickets_router
from .routes.test_whatsapp import router as test_whatsapp_router
from .routes.webhooks import handle_email_message

configure_structured_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="Omnichannel CX Accelerator Phase 1", version="1.0.0")
app.include_router(conversations_router)
app.include_router(tickets_router)
app.include_router(integrations_router)
app.include_router(rag_router)
app.include_router(audit_router)
app.include_router(test_whatsapp_router)


@app.middleware("http")
async def request_logging(request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
        logger.info("http_request", extra={"latency_ms": round((time.perf_counter() - started) * 1000, 2)})
        return response
    except Exception:
        logger.exception("http_request_failed", extra={"latency_ms": round((time.perf_counter() - started) * 1000, 2)})
        raise


@app.get("/")
def root() -> dict:
    return {"name": "Omnichannel CX Accelerator", "phase": 1, "channels": ["whatsapp", "email"], "health": "/health"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "omnichannel-cx-api"}


@app.post("/webhooks/email", response_model=ChannelResponse)
def email_webhook(
    payload: EmailWebhookPayload,
    x_email_webhook_secret: str | None = Header(default=None),
) -> ChannelResponse:
    validate_email_secret(x_email_webhook_secret)
    return handle_email_message(payload)
