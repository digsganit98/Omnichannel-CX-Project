from datetime import datetime, timezone

from pydantic import BaseModel, Field

from shared.schemas.messages import Channel


class ConversationTurn(BaseModel):
    channel: Channel
    customer_text: str
    assistant_text: str
    intent: str
    sentiment: str
    resolved: bool
    ticket_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CustomerProfile(BaseModel):
    customer_id: str
    display_name: str | None = None
    preferred_channel: Channel | None = None
    sentiment_indicator: str = "neutral"
    metadata: dict = Field(default_factory=dict)


class Conversation(BaseModel):
    conversation_id: str
    customer_id: str
    profile: CustomerProfile
    turns: list[ConversationTurn] = Field(default_factory=list)
    summary: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
