from shared.schemas.intents import Intent, IntentResult, Urgency

from .sentiment import detect_sentiment
from .urgency import detect_urgency


KEYWORDS = {
    Intent.HUMAN_ESCALATION:        {"human", "agent", "representative", "speak to someone", "call me"},
    Intent.COMPLAINT:               {"complaint", "terrible", "unacceptable", "angry", "frustrated", "worst service"},
    Intent.FRAUD_REPORT:            {"fraud", "hack", "phishing", "scam", "money stolen", "account hacked", "unauthorized transaction"},
    Intent.TRANSACTION_DISPUTE:     {"dispute", "wrong debit", "incorrect charge", "charge error", "not authorized", "unknown transaction"},
    Intent.FUND_TRANSFER:           {"transfer", "neft", "rtgs", "imps", "send money", "wire transfer", "beneficiary"},
    Intent.ACCOUNT_BALANCE_INQUIRY: {"balance", "account balance", "available funds", "how much in my account", "check balance"},
    Intent.LOAN_STATUS:             {"loan balance", "emi", "repayment", "outstanding loan", "loan status", "loan due", "emi due"},
    Intent.LOAN_APPLICATION:        {"apply loan", "new loan", "personal loan", "home loan", "loan eligibility", "loan apply"},
    Intent.LOAN_DEFAULT_NOTICE:     {"default", "overdue", "missed emi", "npa", "loan overdue", "pending emi"},
    Intent.POLICY_STATUS:           {"policy", "insurance policy", "premium", "policy number", "coverage", "policy status"},
    Intent.CLAIM_STATUS:            {"claim status", "status of my claim", "track my claim", "claim update",
                                     "existing claim", "claim progress"},
    Intent.INSURANCE_CLAIM:         {"claim", "file claim", "submit claim", "make a claim", "accident",
                                     "damage claim", "reimbursement", "hospitalization"},
    Intent.CARD_MANAGEMENT:         {"block card", "lost card", "stolen card", "card limit", "pin change", "debit card", "credit card", "card blocked"},
    Intent.KYC_UPDATE:              {"kyc", "update documents", "pan card", "aadhaar", "address proof", "kyc update", "document update"},
    Intent.TICKET_STATUS:           {"ticket status", "case status", "query status", "reference number",
                                     "status of my", "update on my", "what happened to my",
                                     "my complaint status", "follow up", "ticket number",
                                     "is my request", "any update", "complaint reference"},
}


def classify_intent(text: str) -> IntentResult:
    lowered = text.lower()
    intent_override = _process_or_status_intent(lowered)
    scores = {
        intent: sum(1 for keyword in keywords if keyword in lowered)
        for intent, keywords in KEYWORDS.items()
    }
    intent, score = max(scores.items(), key=lambda item: item[1])
    if intent_override is not None:
        intent = intent_override
        score = max(score, 1)
    elif score == 0:
        intent = Intent.GENERAL_INQUIRY
    sentiment = detect_sentiment(text)
    urgency = Urgency(detect_urgency(text, sentiment))
    confidence = min(0.95, 0.55 + score * 0.12) if score else 0.45
    return IntentResult(
        intent=intent,
        confidence=confidence,
        urgency=urgency,
        sentiment=sentiment,
        reason="Matched BFSI intent rules." if score else "No specific intent keyword matched.",
        analysis_source="rule_fallback",
    )


def _process_or_status_intent(lowered: str) -> Intent | None:
    """Resolve process-vs-account-status phrases before broad keyword scoring."""
    if any(term in lowered for term in ("human", "agent", "representative", "speak to someone", "connect me")):
        return Intent.HUMAN_ESCALATION

    status_terms = ("status", "track", "progress", "update on", "what happened")
    process_terms = ("how do i", "how can i", "steps", "process", "apply", "file", "submit")

    if "claim" in lowered:
        if any(term in lowered for term in status_terms):
            return Intent.CLAIM_STATUS
        if any(term in lowered for term in process_terms):
            return Intent.INSURANCE_CLAIM

    if "loan" in lowered:
        if any(term in lowered for term in status_terms) or "already applied" in lowered:
            return Intent.LOAN_STATUS
        if any(term in lowered for term in process_terms):
            return Intent.LOAN_APPLICATION

    return None
