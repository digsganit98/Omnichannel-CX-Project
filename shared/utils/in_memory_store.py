from collections import defaultdict
from datetime import datetime, timezone

from shared.schemas.conversation import Conversation, CustomerProfile
from shared.schemas.messages import InboundMessage
from shared.schemas.tickets import Ticket
from shared.utils.ids import new_id


class InMemoryStore:
    def __init__(self) -> None:
        self.conversations: dict[str, Conversation] = {}
        self.customer_to_conversation: dict[str, str] = {}
        self.tickets: dict[str, Ticket] = {}
        self.metrics: dict[str, int] = defaultdict(int)

    def get_or_create_conversation(self, message: InboundMessage) -> Conversation:
        conversation_id = self.customer_to_conversation.get(message.customer_id)
        if conversation_id:
            return self.conversations[conversation_id]

        conversation_id = new_id("conv")
        profile = CustomerProfile(
            customer_id=message.customer_id,
            display_name=message.display_name,
            preferred_channel=message.channel,
        )
        conversation = Conversation(
            conversation_id=conversation_id,
            customer_id=message.customer_id,
            profile=profile,
        )
        self.conversations[conversation_id] = conversation
        self.customer_to_conversation[message.customer_id] = conversation_id
        return conversation

    def save_conversation(self, conversation: Conversation) -> None:
        conversation.updated_at = datetime.now(timezone.utc)
        self.conversations[conversation.conversation_id] = conversation

    def save_ticket(self, ticket: Ticket) -> None:
        self.tickets[ticket.ticket_id] = ticket

    def record_metric(self, metric: str) -> None:
        self.metrics[metric] += 1


store = InMemoryStore()
