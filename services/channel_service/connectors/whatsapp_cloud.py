import logging

from shared.schemas.messages import WhatsAppWebhookPayload

from .http import post_json


GRAPH_BASE_URL = "https://graph.facebook.com/v20.0"
logger = logging.getLogger(__name__)


class WhatsAppCloudConnector:
    def __init__(self, access_token: str, phone_number_id: str, graph_base_url: str = GRAPH_BASE_URL) -> None:
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.graph_base_url = graph_base_url.rstrip("/")

    def send_text(self, to: str, text: str) -> dict:
        return post_json(
            f"{self.graph_base_url}/{self.phone_number_id}/messages",
            self.access_token,
            {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": text},
            },
        )


class LocalWhatsAppTestConnector:
    def send_text(self, to: str, text: str) -> dict:
        logger.info("local_whatsapp_test_sent", extra={"channel": "whatsapp", "recipient": to})
        return {
            "provider": "whatsapp_local_test",
            "status": "sent",
            "to": to,
            "text": text,
        }


def verify_webhook(mode: str | None, token: str | None, challenge: str | None, expected_token: str) -> str | None:
    if mode == "subscribe" and token == expected_token and challenge:
        return challenge
    return None


def whatsapp_cloud_webhook_to_payloads(payload: dict) -> list[WhatsAppWebhookPayload]:
    messages: list[WhatsAppWebhookPayload] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = {
                contact.get("wa_id"): contact.get("profile", {}).get("name")
                for contact in value.get("contacts", [])
            }
            for message in value.get("messages", []):
                text = _extract_text(message)
                if not text:
                    continue
                from_number = message.get("from", "")
                messages.append(
                    WhatsAppWebhookPayload(
                        from_=from_number,
                        text=text,
                        profile_name=contacts.get(from_number),
                        message_id=message.get("id"),
                        metadata={
                            "provider": "whatsapp_cloud",
                            "timestamp": message.get("timestamp"),
                            "message_type": message.get("type"),
                            "raw": message,
                        },
                    )
                )
    return messages


def _extract_text(message: dict) -> str | None:
    message_type = message.get("type")
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
