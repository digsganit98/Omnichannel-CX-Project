def extract_topic(text: str) -> str:
    tokens = [token.strip(".,!?").lower() for token in text.split()]
    meaningful = [token for token in tokens if len(token) > 4]
    return meaningful[0] if meaningful else "general"
