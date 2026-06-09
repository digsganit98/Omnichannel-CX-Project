from fastapi import APIRouter, Header

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import validate_email_secret
from shared.schemas.messages import EmailWebhookPayload
from shared.utils.ids import new_id

from .webhooks import handle_email_message

router = APIRouter(prefix="/integrations", tags=["integrations"])


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
