URGENT = {
    "urgent", "asap", "immediately", "critical", "escalate", "complaint",
    # BFSI-specific urgent signals
    "fraud", "blocked", "stolen", "hacked", "overdue", "account hacked",
    "immediate transfer", "money stolen", "unauthorized withdrawal",
}


def detect_urgency(text: str, sentiment: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in URGENT):
        return "high"
    if sentiment == "negative":
        return "medium"
    return "low"
