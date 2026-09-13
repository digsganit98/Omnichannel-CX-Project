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
    UP_SELL = "up_sell"
    # ── The case_advisor vocabulary ───────────────────────────────────────────
    # Every one of these is a REASON TO WRITE TO THE CUSTOMER, which is what the Suggested
    # Actions card is for. Internal chores are deliberately absent - a CRM sync failure is
    # connector health and belongs in System Configuration, and "escalate to senior" is a
    # routing decision, not something anyone says to a customer.
    #
    # PROMISED_UPDATE replaces DRAFT_FOLLOW_UP, which is kept below only so rows already
    # written to agent_assist_recommendations keep resolving. Approving either one creates
    # an editable draft; the others record the decision.
    PROMISED_UPDATE = "promised_update"
    INFORMATION_NEEDED = "information_needed"
    PROACTIVE_WARNING = "proactive_warning"
    ACKNOWLEDGEMENT = "acknowledgement"
    # Superseded by PROMISED_UPDATE. Retained so historic rows do not become unreadable.
    DRAFT_FOLLOW_UP = "draft_follow_up"
    NO_ACTION = "no_action"


# Approving one of these creates an editable reply draft; approving anything else only
# records the decision. Kept as a set so both the decision route and the UI agree on which
# button to offer.
DRAFTABLE_ACTION_TYPES = {ActionType.PROMISED_UPDATE.value, ActionType.DRAFT_FOLLOW_UP.value}


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
