import os

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from services.channel_service.connectors.gmail_api import GmailConnector, gmail_pubsub_notification
from services.channel_service.connectors.outlook_graph import OutlookGraphConnector
from services.channel_service.connectors.whatsapp_cloud import (
    verify_webhook,
    whatsapp_cloud_webhook_to_payloads,
)
from shared.utils.in_memory_store import store

from .webhooks import handle_email_message, handle_whatsapp_message

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/whatsapp/webhook", response_class=PlainTextResponse)
def verify_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> str:
    expected_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    challenge = verify_webhook(hub_mode, hub_verify_token, hub_challenge, expected_token)
    if challenge is None:
        raise HTTPException(status_code=403, detail="Invalid WhatsApp verification token")
    return challenge


@router.post("/whatsapp/webhook")
async def receive_whatsapp_cloud_webhook(request: Request) -> list[dict]:
    raw_payload = await request.json()
    payloads = whatsapp_cloud_webhook_to_payloads(raw_payload)
    responses = []
    for payload in payloads:
        response = handle_whatsapp_message(payload)
        store.record_metric("whatsapp_messages")
        responses.append(response.model_dump())
    return responses


@router.post("/outlook/pull")
def pull_outlook_messages(limit: int = 10) -> list[dict]:
    token = os.getenv("OUTLOOK_ACCESS_TOKEN")
    if not token:
        raise HTTPException(status_code=400, detail="OUTLOOK_ACCESS_TOKEN is not configured")
    payloads = OutlookGraphConnector(token).fetch_recent_messages(limit=limit)
    responses = []
    for payload in payloads:
        response = handle_email_message(payload)
        store.record_metric("email_messages")
        responses.append(response.model_dump())
    return responses


@router.get("/outlook/webhook", response_class=PlainTextResponse)
def validate_outlook_webhook(validationToken: str | None = None) -> str:
    if not validationToken:
        raise HTTPException(status_code=400, detail="Missing validationToken")
    return validationToken


@router.post("/outlook/webhook")
async def receive_outlook_webhook(
    request: Request,
    validationToken: str | None = None,
):
    if validationToken:
        return PlainTextResponse(validationToken)
    token = os.getenv("OUTLOOK_ACCESS_TOKEN")
    if not token:
        raise HTTPException(status_code=400, detail="OUTLOOK_ACCESS_TOKEN is not configured")
    payload = await request.json()
    connector = OutlookGraphConnector(token)
    responses = []
    for notification in payload.get("value", []):
        resource = notification.get("resource")
        if not resource:
            continue
        email_payload = connector.fetch_message_by_resource(resource)
        response = handle_email_message(email_payload)
        store.record_metric("email_messages")
        responses.append(response.model_dump())
    return responses


@router.post("/gmail/pull")
def pull_gmail_messages(limit: int = 10, query: str = "newer_than:7d") -> list[dict]:
    token = os.getenv("GMAIL_ACCESS_TOKEN")
    if not token:
        raise HTTPException(status_code=400, detail="GMAIL_ACCESS_TOKEN is not configured")
    payloads = GmailConnector(token).fetch_recent_messages(limit=limit, query=query)
    responses = []
    for payload in payloads:
        response = handle_email_message(payload)
        store.record_metric("email_messages")
        responses.append(response.model_dump())
    return responses


@router.post("/gmail/webhook")
async def receive_gmail_pubsub_webhook(request: Request) -> dict:
    token = os.getenv("GMAIL_ACCESS_TOKEN")
    if not token:
        raise HTTPException(status_code=400, detail="GMAIL_ACCESS_TOKEN is not configured")
    payload = await request.json()
    notification = gmail_pubsub_notification(payload)
    history_id = notification.get("historyId")
    if not history_id:
        return {"processed": 0, "reason": "No Gmail historyId found"}
    email_payloads = GmailConnector(token).fetch_history_messages(history_id)
    responses = []
    for email_payload in email_payloads:
        response = handle_email_message(email_payload)
        store.record_metric("email_messages")
        responses.append(response.model_dump())
    return {"processed": len(responses), "responses": responses}
