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
}
POSITIVE = {"thanks", "great", "good", "helpful", "resolved"}


def detect_sentiment(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in NEGATIVE):
        return "negative"
    if any(word in lowered for word in POSITIVE):
        return "positive"
    return "neutral"
