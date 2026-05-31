from shared.schemas.intents import Intent, IntentResult, Urgency

from .sentiment import detect_sentiment
from .urgency import detect_urgency


KEYWORDS = {
    Intent.HUMAN_ESCALATION: {"human", "agent", "representative", "speak to someone", "call me"},
    Intent.COMPLAINT: {"complaint", "terrible", "unacceptable", "angry", "frustrated"},
    Intent.RETURN_REQUEST: {"return", "send back", "exchange"},
    Intent.REFUND_REQUEST: {"refund", "money back", "not credited"},
    Intent.BILLING_ISSUE: {"invoice", "bill", "charged", "payment", "paid", "charged twice"},
    Intent.TECHNICAL_SUPPORT: {"error", "not working", "failed", "bug", "login", "password"},
    Intent.ORDER_TRACKING: {"order", "track", "delivery", "shipment", "where is"},
    Intent.PRODUCT_INFORMATION: {"product", "size", "color", "available", "stock", "warranty", "specification"},
}


def classify_intent(text: str) -> IntentResult:
    lowered = text.lower()
    scores = {
        intent: sum(1 for keyword in keywords if keyword in lowered)
        for intent, keywords in KEYWORDS.items()
    }
    intent, score = max(scores.items(), key=lambda item: item[1])
    if score == 0:
        intent = Intent.GENERAL_INQUIRY
    sentiment = detect_sentiment(text)
    urgency = Urgency(detect_urgency(text, sentiment))
    confidence = min(0.95, 0.55 + score * 0.12) if score else 0.45
    return IntentResult(
        intent=intent,
        confidence=confidence,
        urgency=urgency,
        sentiment=sentiment,
        reason="Matched Phase 1 intent rules." if score else "No specific intent keyword matched.",
        analysis_source="rule_fallback",
    )
