NEGATIVE = {
    "angry",
    "bad",
    "terrible",
    "frustrated",
    "late",
    "failed",
    "problem",
    "damaged",
    "not received",
    "not credited",
    "charged twice",
    "cancel my order",
    "cancel the order",
    "connect me to a human",
    "human agent",
    "human representative",
}
POSITIVE = {"thanks", "great", "good", "helpful", "resolved"}


def detect_sentiment(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in NEGATIVE):
        return "negative"
    if any(word in lowered for word in POSITIVE):
        return "positive"
    return "neutral"
