from shared.schemas.conversation import Conversation, ConversationTurn
from shared.schemas.messages import InboundMessage
from shared.utils.in_memory_store import store

from .summarizer import summarize_conversation


class ConversationManager:
    def load(self, message: InboundMessage) -> Conversation:
        return store.get_or_create_conversation(message)

    def append_turn(self, conversation: Conversation, turn: ConversationTurn) -> Conversation:
        conversation.turns.append(turn)
        conversation.summary = summarize_conversation(conversation)
        store.save_conversation(conversation)
        return conversation
