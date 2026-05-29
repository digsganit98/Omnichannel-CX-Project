from services.ticket_service.assignment import assign_team
from shared.schemas.conversation import Conversation
from shared.schemas.messages import InboundMessage
from shared.schemas.tickets import Ticket, TicketPriority
from shared.utils.ids import new_id
from shared.utils.in_memory_store import store


class TicketManager:
    def create_ticket(
        self,
        conversation: Conversation,
        message: InboundMessage,
        intent: str,
        urgency: str,
    ) -> Ticket:
        priority = TicketPriority.HIGH if urgency == "high" else TicketPriority.MEDIUM
        ticket = Ticket(
            ticket_id=new_id("tkt"),
            conversation_id=conversation.conversation_id,
            customer_id=message.customer_id,
            title=message.subject or f"{intent.replace('_', ' ').title()} request",
            description=message.text,
            intent=intent,
            priority=priority,
            assigned_team=assign_team(intent),
        )
        store.save_ticket(ticket)
        return ticket
