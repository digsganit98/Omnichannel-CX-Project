import os

import httpx

from services.channel_adapter import BaseChannelAdapter, OutboundMessage
from shared.schemas.messages import Channel, InboundMessage
from shared.utils.ids import new_id


def _normalize_wa_recipient(to_id: str) -> str:
    """Ensure the WhatsApp recipient number is in Meta's expected format.

    A customer's number can be stored bare ('7890864700') because the inbound
    path only does `.lstrip('+')` — but Meta rejects a bare 10-digit number with
    400 '(#131030) Recipient phone number not in allowed list'. Prepend the Indian
    country code (91) when the number is a bare 10-digit; leave an already-prefixed
    number (12-digit starting '91') or any other format unchanged. India-only
    assumption — safe here because all BFSI data is Indian.
    """
    digits = "".join(c for c in (to_id or "") if c.isdigit())
    if not digits:
        return to_id
    if len(digits) == 10:
        return "91" + digits
    return digits


class WhatsAppMetaAdapter(BaseChannelAdapter):
    channel = Channel.WHATSAPP

    def parse_inbound(self, payload: dict) -> InboundMessage:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                contacts = {
                    item.get("wa_id"): item.get("profile", {}).get("name")
                    for item in value.get("contacts", [])
                }
                for message in value.get("messages", []):
                    text = self._extract_text(message)
                    if not text:
                        continue
                    from_id = str(message.get("from", "")).strip().lstrip("+")
                    return InboundMessage(
                        channel=Channel.WHATSAPP,
                        channel_identifier=from_id,
                        display_name=contacts.get(from_id),
                        text=text,
                        provider="whatsapp_cloud",
                        external_message_id=message.get("id"),
                        correlation_id=new_id("corr"),
                        metadata={
                            "provider": "whatsapp_cloud",
                            "timestamp": message.get("timestamp"),
                            "message_type": message.get("type", "text"),
                            "raw": message,
                        },
                        profile_metadata={"phone": from_id},
                    )
        raise ValueError("No supported WhatsApp inbound message found")

    async def send_outbound(self, message: OutboundMessage) -> dict:
        phone_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
        access_token = os.environ["WHATSAPP_ACCESS_TOKEN"]
        url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": _normalize_wa_recipient(message.to_id),
                    "type": "text",
                    "text": {"body": message.text},
                },
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _extract_text(message: dict) -> str | None:
        message_type = message.get("type", "text")
        if message_type == "text":
            return message.get("text", {}).get("body")
        if message_type == "button":
            return message.get("button", {}).get("text")
        if message_type == "interactive":
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                return interactive.get("button_reply", {}).get("title")
            if interactive.get("type") == "list_reply":
                return interactive.get("list_reply", {}).get("title")
        return None
