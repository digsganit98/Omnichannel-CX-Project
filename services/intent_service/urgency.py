URGENT = {"urgent", "asap", "immediately", "critical", "escalate", "complaint"}


def detect_urgency(text: str, sentiment: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in URGENT):
        return "high"
    if sentiment == "negative":
        return "medium"
    return "low"
