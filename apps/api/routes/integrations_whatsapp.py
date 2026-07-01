import json
import os

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from apps.api.dependencies.security import validate_whatsapp_signature
from services.channel_adapter import ChannelAdapterRegistry
from services.channel_service.connectors.whatsapp_cloud import verify_webhook, whatsapp_cloud_webhook_to_statuses
from shared.schemas.messages import Channel

from .integrations import _record_whatsapp_status
from . import webhooks

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


@router.post("/whatsapp/webhook", status_code=status.HTTP_202_ACCEPTED)
async def receive_whatsapp_cloud_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
) -> dict:
    body = await request.body()
    validate_whatsapp_signature(body, x_hub_signature_256)
    payload = json.loads(body or b"{}")
    adapter = ChannelAdapterRegistry.get(Channel.WHATSAPP)
    messages = []
    try:
        inbound = adapter.parse_inbound(payload)
        messages.append(webhooks.get_router().handle(inbound).model_dump(mode="json"))
    except ValueError:
        pass
    statuses = [_record_whatsapp_status(item) for item in whatsapp_cloud_webhook_to_statuses(payload)]
    return {
        "messages_received": len(messages),
        "statuses_received": len(statuses),
        "messages": messages,
        "statuses": statuses,
    }
