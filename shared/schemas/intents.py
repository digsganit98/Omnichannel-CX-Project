from enum import StrEnum

from pydantic import BaseModel, Field


class Intent(StrEnum):
    ORDER_TRACKING = "order_tracking"
    REFUND_REQUEST = "refund_request"
    RETURN_REQUEST = "return_request"
    PRODUCT_INFORMATION = "product_information"
    BILLING_ISSUE = "billing_issue"
    TECHNICAL_SUPPORT = "technical_support"
    COMPLAINT = "complaint"
    GENERAL_INQUIRY = "general_inquiry"
    HUMAN_ESCALATION = "human_escalation"


class Urgency(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IntentResult(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    urgency: Urgency
    reason: str
    sentiment: str = "neutral"
    analysis_source: str = "rule_fallback"
