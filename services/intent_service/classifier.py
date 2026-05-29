KEYWORDS = {
    "refund_request": {"refund", "return", "cancel", "money back"},
    "billing_issue": {"invoice", "bill", "charged", "payment", "paid", "payment issue"},
    "technical_support": {"error", "not working", "failed", "bug", "login", "password"},
    "order_tracking": {"order", "track", "delivery", "shipment", "where is"},
}


def classify_intent(text: str) -> str:
    lowered = text.lower()
    scores = {
        intent: sum(1 for keyword in keywords if keyword in lowered)
        for intent, keywords in KEYWORDS.items()
    }
    priority = {"refund_request": 4, "billing_issue": 3, "technical_support": 2, "order_tracking": 1}
    best_intent, best_score = max(scores.items(), key=lambda item: (item[1], priority.get(item[0], 0)))
    if best_score > 0:
        return best_intent
    return "general_question"
