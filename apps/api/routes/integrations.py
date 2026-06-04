import json
import os

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import validate_email_secret, validate_whatsapp_signature
from services.channel_service.connectors.whatsapp_cloud import (
    verify_webhook,
    whatsapp_cloud_webhook_to_payloads,
    whatsapp_cloud_webhook_to_statuses,
)
from shared.schemas.messages import EmailWebhookPayload
from shared.utils.ids import new_id

from .webhooks import handle_email_message, handle_whatsapp_message

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/whatsapp/webhook", response_class=PlainTextResponse)
def verify_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> str:
    challenge = verify_webhook(hub_mode, hub_verify_token, hub_challenge, os.getenv("WHATSAPP_VERIFY_TOKEN", ""))
    if challenge is None:
        raise HTTPException(status_code=403, detail="Invalid WhatsApp verification token")
    return challenge


@router.post("/whatsapp/webhook")
async def receive_whatsapp_cloud_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
) -> dict:
    body = await request.body()
    validate_whatsapp_signature(body, x_hub_signature_256)
    payload = json.loads(body)
    payloads = whatsapp_cloud_webhook_to_payloads(payload)
    statuses = whatsapp_cloud_webhook_to_statuses(payload)
    message_results = [handle_whatsapp_message(item).model_dump(mode="json") for item in payloads]
    status_results = [_record_whatsapp_status(status) for status in statuses]
    return {
        "messages_received": len(message_results),
        "statuses_received": len(status_results),
        "messages": message_results,
        "statuses": status_results,
    }


def _record_whatsapp_status(status: dict) -> dict:
    repo = get_repository()
    recorded = repo.record_whatsapp_delivery_status(status)
    repo.add_audit_event(
        "whatsapp_delivery_status_received",
        new_id("corr"),
        channel="whatsapp",
        message_id=status["provider_message_id"],
        conversation_id=recorded.get("conversation_id"),
        details={
            "provider_message_id": status["provider_message_id"],
            "status": status["status"],
            "recipient_id": status.get("recipient_id"),
            "turn_id": recorded.get("turn_id"),
            "error_code": status.get("error_code"),
            "error_title": status.get("error_title"),
            "error_details": status.get("error_details"),
        },
    )
    return recorded


@router.post("/email/webhook")
async def receive_email_webhook(
    payload: EmailWebhookPayload,
    x_email_webhook_secret: str | None = Header(default=None),
) -> dict:
    validate_email_secret(x_email_webhook_secret)
    payload.metadata.setdefault("provider", "email_webhook")
    return handle_email_message(payload).model_dump(mode="json")
