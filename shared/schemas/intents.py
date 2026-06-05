from enum import StrEnum

from pydantic import BaseModel, Field


class Intent(StrEnum):
    ACCOUNT_BALANCE_INQUIRY = "account_balance_inquiry"
    TRANSACTION_DISPUTE     = "transaction_dispute"
    FUND_TRANSFER           = "fund_transfer"
    LOAN_STATUS             = "loan_status"
    LOAN_APPLICATION        = "loan_application"
    LOAN_DEFAULT_NOTICE     = "loan_default_notice"
    POLICY_STATUS           = "policy_status"
    INSURANCE_CLAIM         = "insurance_claim"
    CARD_MANAGEMENT         = "card_management"
    KYC_UPDATE              = "kyc_update"
    FRAUD_REPORT            = "fraud_report"
    COMPLAINT               = "complaint"
    TICKET_STATUS           = "ticket_status"
    GENERAL_INQUIRY         = "general_inquiry"
    HUMAN_ESCALATION        = "human_escalation"


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
    secondary_intent: Intent | None = None
    language: str = "en"
