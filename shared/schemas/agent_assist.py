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
    # The customer's own words suggested their case is finished. NOT part of the
    # case_advisor vocabulary above: the model never produces this one and must never be
    # able to, because inventing "they sound done" is precisely the failure that let a
    # "thank you" close a live fraud dispute. It is raised by the pipeline from what the
    # customer actually said (graph.py _propose_close writes the permanent record to
    # ticket_events) and this row is the work-item the agent decides on.
    READY_TO_CLOSE = "ready_to_close"


# Approving one of these creates an editable reply draft; approving anything else only
# records the decision. Kept as a set so both the decision route and the UI agree on which
# button to offer.
DRAFTABLE_ACTION_TYPES = {ActionType.PROMISED_UPDATE.value, ActionType.DRAFT_FOLLOW_UP.value}

# Raised by the PIPELINE, not by case_advisor. The Suggested Actions route retires any
# pending row the advisor no longer returns - which is correct for advice, and fatal for
# anything the advisor never produces: the LLM cannot name `ready_to_close`, so without
# this exemption every proposal would be superseded by the very next card refresh, seconds
# after the customer raised it. Same escape hatch the offer types already use.
PIPELINE_ACTION_TYPES = {ActionType.READY_TO_CLOSE.value}


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
