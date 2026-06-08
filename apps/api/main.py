import logging
import os
import time
from pathlib import Path

# Load .env before anything else so all os.getenv() calls see the values
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
except ImportError:
    pass

from fastapi import FastAPI, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.api.dependencies.security import validate_email_secret
from shared.logging.structured import configure_structured_logging
from shared.schemas.messages import EmailWebhookPayload
from shared.schemas.responses import ChannelResponse

from .routes.admin_auth import router as admin_auth_router
from .routes.analytics import router as analytics_router
from .routes.audit import router as audit_router
from .routes.auth import router as auth_router
from .routes.conversations import router as conversations_router
from .routes.customers import router as customers_router
from .routes.crm import router as crm_router
from .routes.email import router as email_router
from .routes.integrations_whatsapp import router as integrations_whatsapp_router
from .routes.integrations import router as integrations_router
from .routes.neo4j_admin import router as neo4j_admin_router
from .routes.orchestration import router as orchestration_router
from .routes.rag import router as rag_router
from .routes.tickets import router as tickets_router
from .routes.neo4j_admin import router as neo4j_admin_router
from .routes.test_whatsapp import router as test_whatsapp_router
from .routes.user_portal import router as user_portal_router
from .routes.webhooks import handle_email_message
from .routes.whatsapp import router as whatsapp_router

configure_structured_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="Omnichannel CX Accelerator", version="2.0.0")


@app.on_event("startup")
def _seed_neo4j() -> None:
    if os.getenv("NEO4J_ENABLED", "true").lower() != "true":
        return
    try:
        from services.neo4j_service.client import Neo4jClient
        from services.neo4j_service.loader import load_bfsi_data
        client = Neo4jClient()
        existing = client.query("MATCH (c:Customer) RETURN count(c) AS n")
        if existing and existing[0].get("n", 0) > 0:
            logger.info("neo4j_seed_skipped: data already present")
            client.close()
            return
        counts = load_bfsi_data(client)
        logger.info("neo4j_seed_complete", extra=counts)
        client.close()
    except Exception:
        logger.exception("neo4j_seed_failed")
app.include_router(admin_auth_router)
app.include_router(auth_router)
app.include_router(analytics_router)
app.include_router(conversations_router)
app.include_router(customers_router)
app.include_router(crm_router)
app.include_router(email_router)
app.include_router(tickets_router)
app.include_router(integrations_whatsapp_router)
app.include_router(integrations_router)
app.include_router(neo4j_admin_router)
app.include_router(orchestration_router)
app.include_router(rag_router)
app.include_router(audit_router)
app.include_router(neo4j_admin_router)
app.include_router(test_whatsapp_router)
app.include_router(user_portal_router)
app.include_router(whatsapp_router)

ADMIN_UI_ROOT = Path(__file__).resolve().parents[1] / "admin-ui"
app.mount("/admin-ui/assets", StaticFiles(directory=ADMIN_UI_ROOT), name="admin-ui-assets")


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
    return {
        "name": "Omnichannel CX Accelerator",
        "phase": 2,
        "implemented_phases": [1, 2],
        "channels": ["whatsapp", "email"],
        "health": "/health",
        "admin_ui": "/admin-ui",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "omnichannel-cx-api"}


@app.get("/admin-ui", include_in_schema=False)
def admin_ui() -> FileResponse:
    return FileResponse(ADMIN_UI_ROOT / "index.html")



@app.post("/webhooks/email", response_model=ChannelResponse)
def email_webhook(
    payload: EmailWebhookPayload,
    x_email_webhook_secret: str | None = Header(default=None),
) -> ChannelResponse:
    validate_email_secret(x_email_webhook_secret)
    return handle_email_message(payload)
