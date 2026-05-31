from services.persistence_service.repository import CXRepository
from services.ticket_service.assignment import assign_team
from shared.schemas.intents import Intent, Urgency
from shared.schemas.messages import InboundMessage
from shared.schemas.tickets import Ticket, TicketPriority
from shared.utils.ids import new_id


class TicketManager:
    def __init__(self, repository: CXRepository) -> None:
        self.repository = repository

    def create_or_get_ticket(
        self,
        conversation_id: str,
        customer_id: str,
        message: InboundMessage,
        intent: Intent,
        urgency: Urgency,
    ) -> Ticket:
        existing = self.repository.find_active_ticket(conversation_id)
        if existing:
            return existing
        priority = TicketPriority.HIGH if urgency == Urgency.HIGH else TicketPriority.MEDIUM
        return self.repository.create_ticket(
            Ticket(
                ticket_id=new_id("tkt"),
                conversation_id=conversation_id,
                customer_id=customer_id,
                title=message.subject or f"{intent.value.replace('_', ' ').title()} request",
                description=message.text,
                intent=intent.value,
                priority=priority,
                assigned_team=assign_team(intent.value),
            )
        )
