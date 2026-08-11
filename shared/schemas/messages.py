from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Channel(StrEnum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    WEB_CHAT = "web_chat"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class WhatsAppWebhookPayload(BaseModel):
    from_: str = Field(alias="from")
    text: str
    profile_name: str | None = None
    message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class EmailWebhookPayload(BaseModel):
    from_email: str
    subject: str
    body: str
    message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebChatWebhookPayload(BaseModel):
    session_id: str
    text: str
    display_name: str | None = None
    message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InboundMessage(BaseModel):
    channel: Channel
    channel_identifier: str
    text: str
    provider: str
    subject: str | None = None
    display_name: str | None = None
    external_message_id: str | None = None
    correlation_id: str
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)
    profile_metadata: dict[str, Any] = Field(default_factory=dict)
