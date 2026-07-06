def should_escalate(urgency: str, sentiment: str) -> bool:
    return urgency == "high" or sentiment == "negative"
