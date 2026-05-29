from html import unescape
from re import sub

from shared.schemas.messages import EmailWebhookPayload

from .http import get_json


GRAPH_MESSAGES_URL = "https://graph.microsoft.com/v1.0/me/messages"


class OutlookGraphConnector:
    def __init__(self, access_token: str, messages_url: str = GRAPH_MESSAGES_URL) -> None:
        self.access_token = access_token
        self.messages_url = messages_url

    def fetch_recent_messages(self, limit: int = 10) -> list[EmailWebhookPayload]:
        response = get_json(
            self.messages_url,
            self.access_token,
            {
                "$top": str(limit),
                "$orderby": "receivedDateTime desc",
                "$select": "id,subject,from,bodyPreview,body,receivedDateTime,internetMessageId",
            },
        )
        return [outlook_message_to_email_payload(item) for item in response.get("value", [])]

    def fetch_message_by_resource(self, resource: str) -> EmailWebhookPayload:
        resource = resource.lstrip("/")
        if resource.startswith("me/messages/"):
            url = f"https://graph.microsoft.com/v1.0/{resource}"
        elif resource.startswith("users/"):
            url = f"https://graph.microsoft.com/v1.0/{resource}"
        else:
            url = f"https://graph.microsoft.com/v1.0/me/messages/{resource}"
        message = get_json(
            url,
            self.access_token,
            {"$select": "id,subject,from,bodyPreview,body,receivedDateTime,internetMessageId"},
        )
        return outlook_message_to_email_payload(message)


def outlook_message_to_email_payload(message: dict) -> EmailWebhookPayload:
    sender = (
        message.get("from", {})
        .get("emailAddress", {})
        .get("address", "unknown-outlook-sender@example.com")
    )
    subject = message.get("subject") or "(no subject)"
    body = _body_text(message)
    return EmailWebhookPayload(
        from_email=sender,
        subject=subject,
        body=body,
        message_id=message.get("internetMessageId") or message.get("id"),
        metadata={
            "provider": "outlook",
            "graph_id": message.get("id"),
            "received_at": message.get("receivedDateTime"),
        },
    )


def _body_text(message: dict) -> str:
    body = message.get("body") or {}
    content = body.get("content") or message.get("bodyPreview") or ""
    if body.get("contentType", "").lower() == "html":
        content = sub(r"<[^>]+>", " ", content)
    return " ".join(unescape(content).split())
