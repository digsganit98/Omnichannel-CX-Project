from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Channel(StrEnum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    WEBCHAT = "webchat"
    VOICE = "voice"


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


class InboundMessage(BaseModel):
    channel: Channel
    customer_id: str
    text: str
    subject: str | None = None
    display_name: str | None = None
    external_message_id: str | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)
