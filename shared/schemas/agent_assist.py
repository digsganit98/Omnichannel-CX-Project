from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ActionType(StrEnum):
    ESCALATE_TO_SENIOR = "escalate_to_senior"
    PROACTIVE_OUTREACH = "proactive_outreach"
    OFFER_RETENTION = "offer_retention"
    REQUEST_DOCUMENT = "request_document"
    CROSS_SELL = "cross_sell"
    NO_ACTION = "no_action"


class NextBestAction(BaseModel):
    action_type: ActionType
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    priority: int = 0
    metadata: dict = Field(default_factory=dict)


class NBARecommendationSet(BaseModel):
    conversation_id: str
    customer_id: str
    ticket_id: str | None = None
    actions: list[NextBestAction] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NBADecisionUpdate(BaseModel):
    status: Literal["approved", "dismissed"]
    actor: str = "admin"
