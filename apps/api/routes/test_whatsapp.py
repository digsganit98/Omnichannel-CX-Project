import logging
import os

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import validate_local_whatsapp_test_signature
from services.channel_service.connectors.whatsapp_cloud import LocalWhatsAppTestConnector, WhatsAppCloudConnector
from shared.schemas.messages import WhatsAppWebhookPayload
from shared.utils.ids import new_id

from .webhooks import handle_whatsapp_message

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/test/whatsapp", tags=["local-whatsapp-test"])


class LocalWhatsAppInbound(BaseModel):
    from_: str = Field(alias="from")
    text: str
    profile_name: str | None = "Local WhatsApp Tester"
    message_id: str | None = None
    outbound_provider: str = "local_mock"
    metadata: dict = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class LocalWhatsAppSend(BaseModel):
    to: str
    text: str
    provider: str = "local_mock"


@router.post("/inbound-simulate")
def simulate_whatsapp_inbound(
    payload: LocalWhatsAppInbound,
    x_test_whatsapp_signature: str | None = Header(default=None),
) -> dict:
    validate_local_whatsapp_test_signature(x_test_whatsapp_signature)
    message_id = payload.message_id or new_id("wa_local")
    logger.info("local_whatsapp_test_inbound", extra={"channel": "whatsapp", "message_id": message_id})
    webhook_payload = WhatsAppWebhookPayload(
        from_=payload.from_,
        text=payload.text,
        profile_name=payload.profile_name,
        message_id=message_id,
        metadata={
            **payload.metadata,
            "provider": _inbound_provider(payload.outbound_provider),
            "test_mode": True,
            "outbound_provider": payload.outbound_provider,
            "raw_reference": "local-whatsapp-simulation",
        },
    )
    return handle_whatsapp_message(webhook_payload).model_dump(mode="json")


@router.post("/send")
def simulate_whatsapp_send(
    payload: LocalWhatsAppSend,
    x_test_whatsapp_signature: str | None = Header(default=None),
) -> dict:
    validate_local_whatsapp_test_signature(x_test_whatsapp_signature)
    correlation_id = new_id("corr")
    logger.info(
        "local_whatsapp_test_manual_send",
        extra={"channel": "whatsapp", "correlation_id": correlation_id},
    )
    connector = _outbound_connector(payload.provider)
    try:
        result = connector.send_text(payload.to, payload.text)
        details = {"provider": payload.provider, "status": "sent", "provider_response": result}
        get_repository().add_audit_event(
            "local_whatsapp_test_sent",
            correlation_id,
            channel="whatsapp",
            details=details,
        )
        return {"correlation_id": correlation_id, **details}
    except Exception as exc:
        logger.exception(
            "local_whatsapp_test_manual_send_failed",
            extra={"channel": "whatsapp", "correlation_id": correlation_id},
        )
        details = {"provider": payload.provider, "status": "failed", "error": str(exc)}
        get_repository().add_audit_event(
            "local_whatsapp_test_send_failed",
            correlation_id,
            channel="whatsapp",
            details=details,
        )
        raise HTTPException(status_code=502, detail=details) from exc


def _outbound_connector(provider: str):
    if provider == "local_mock":
        return LocalWhatsAppTestConnector()
    if provider == "meta":
        access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
        phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        if not access_token or not phone_number_id:
            raise HTTPException(
                status_code=503,
                detail="WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID are required for a Meta outbound test",
            )
        return WhatsAppCloudConnector(access_token, phone_number_id)
    raise HTTPException(status_code=400, detail="provider must be local_mock or meta")


def _inbound_provider(outbound_provider: str) -> str:
    if outbound_provider == "local_mock":
        return "whatsapp_local_test"
    if outbound_provider == "meta":
        _validate_meta_config()
        return "whatsapp_cloud"
    raise HTTPException(status_code=400, detail="outbound_provider must be local_mock or meta")


def _validate_meta_config() -> None:
    if not os.getenv("WHATSAPP_ACCESS_TOKEN") or not os.getenv("WHATSAPP_PHONE_NUMBER_ID"):
        raise HTTPException(
            status_code=503,
            detail="WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID are required for Meta outbound delivery",
        )
