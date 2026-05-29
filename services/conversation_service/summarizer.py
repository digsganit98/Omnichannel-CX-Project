from shared.schemas.conversation import Conversation


def summarize_conversation(conversation: Conversation) -> str:
    recent = conversation.turns[-3:]
    if not recent:
        return ""
    parts = [f"{turn.intent}: {turn.customer_text[:80]}" for turn in recent]
    return " | ".join(parts)
