import os

from fastapi import APIRouter, Depends, Query

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_key

router = APIRouter(prefix="/admin/whatsapp", tags=["admin"], dependencies=[Depends(require_admin_key)])


@router.get("/status")
def whatsapp_status() -> dict:
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN")
    app_secret = os.getenv("WHATSAPP_APP_SECRET")
    business_account_id = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
    return {
        "provider": "meta_whatsapp_cloud",
        "access_token_configured": bool(access_token),
        "phone_number_id_configured": bool(phone_number_id),
        "business_account_id_configured": bool(business_account_id),
        "verify_token_configured": bool(verify_token),
        "app_secret_configured": bool(app_secret),
        "meta_outbound_ready": bool(access_token and phone_number_id),
        "meta_webhook_ready": bool(verify_token and app_secret),
    }


@router.get("/delivery-statuses")
def whatsapp_delivery_statuses(
    provider_message_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    return get_repository().list_whatsapp_delivery_statuses(provider_message_id, limit)
