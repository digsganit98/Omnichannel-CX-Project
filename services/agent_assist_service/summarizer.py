from shared.schemas.conversation import Conversation


def summarize_for_agent(conversation: Conversation) -> str:
    return conversation.summary or "No prior context available."
