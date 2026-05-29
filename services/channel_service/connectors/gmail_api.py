import base64
from email.message import Message
from email.parser import Parser

from shared.schemas.messages import EmailWebhookPayload

from .http import get_json


GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"


class GmailConnector:
    def __init__(self, access_token: str, messages_url: str = GMAIL_MESSAGES_URL) -> None:
        self.access_token = access_token
        self.messages_url = messages_url.rstrip("/")

    def fetch_recent_messages(self, limit: int = 10, query: str = "newer_than:7d") -> list[EmailWebhookPayload]:
        listing = get_json(
            self.messages_url,
            self.access_token,
            {"maxResults": str(limit), "q": query},
        )
        payloads = []
        for item in listing.get("messages", []):
            raw = get_json(
                f"{self.messages_url}/{item['id']}",
                self.access_token,
                {"format": "raw"},
            )
            payloads.append(gmail_raw_message_to_email_payload(raw))
        return payloads

    def fetch_message_by_id(self, message_id: str) -> EmailWebhookPayload:
        raw = get_json(
            f"{self.messages_url}/{message_id}",
            self.access_token,
            {"format": "raw"},
        )
        return gmail_raw_message_to_email_payload(raw)

    def fetch_history_messages(self, start_history_id: str, limit: int = 10) -> list[EmailWebhookPayload]:
        history_url = self.messages_url.rsplit("/messages", 1)[0] + "/history"
        history = get_json(
            history_url,
            self.access_token,
            {
                "startHistoryId": start_history_id,
                "historyTypes": "messageAdded",
                "maxResults": str(limit),
            },
        )
        seen: set[str] = set()
        payloads: list[EmailWebhookPayload] = []
        for item in history.get("history", []):
            for added in item.get("messagesAdded", []):
                message_id = added.get("message", {}).get("id")
                if message_id and message_id not in seen:
                    seen.add(message_id)
                    payloads.append(self.fetch_message_by_id(message_id))
        return payloads


def gmail_pubsub_notification(payload: dict) -> dict:
    data = payload.get("message", {}).get("data")
    if not data:
        return {}
    decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
    import json

    return json.loads(decoded)


def gmail_raw_message_to_email_payload(message: dict) -> EmailWebhookPayload:
    raw = message.get("raw", "")
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", errors="replace")
    parsed = Parser().parsestr(decoded)
    return EmailWebhookPayload(
        from_email=_header_address(parsed.get("From", "unknown-gmail-sender@example.com")),
        subject=parsed.get("Subject", "(no subject)"),
        body=_message_body(parsed),
        message_id=parsed.get("Message-ID") or message.get("id"),
        metadata={
            "provider": "gmail",
            "gmail_id": message.get("id"),
            "thread_id": message.get("threadId"),
        },
    )


def _header_address(value: str) -> str:
    if "<" in value and ">" in value:
        return value.split("<", 1)[1].split(">", 1)[0].strip()
    return value.strip()


def _message_body(message: Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()
        return ""
    payload = message.get_payload(decode=True)
    if payload:
        return payload.decode(message.get_content_charset() or "utf-8", errors="replace").strip()
    return str(message.get_payload() or "").strip()
