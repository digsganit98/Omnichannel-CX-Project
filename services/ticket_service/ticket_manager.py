from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.crm_service.client import CRMClient
from services.persistence_service.repository import CXRepository
from services.ticket_service.assignment import assign_team
from services.workflow_service.approvals import requires_approval
from services.workflow_service.sla import sla_hours
from shared.schemas.intents import Intent, Urgency
from shared.schemas.messages import InboundMessage
from shared.schemas.tickets import Ticket, TicketPriority, TicketStatus
from shared.utils.ids import new_id


class TicketManager:
    def __init__(self, repository: CXRepository, crm: CRMClient | None = None) -> None:
        self.repository = repository
        self.crm = crm or CRMClient()

    def create_or_get_ticket(
        self,
        conversation_id: str,
        customer_id: str,
        message: InboundMessage,
        intent: Intent,
        urgency: Urgency,
        escalation_reason: str | None = None,
        customer: dict | None = None,
    ) -> Ticket:
        existing = self.repository.find_active_ticket_for_intent(conversation_id, intent.value)
        if existing:
            return existing
        priority = TicketPriority.HIGH if urgency == Urgency.HIGH else TicketPriority.MEDIUM
        ticket = Ticket(
            ticket_id=new_id("tkt"),
            conversation_id=conversation_id,
            customer_id=customer_id,
            title=message.subject or f"{intent.value.replace('_', ' ').title()} request",
            description=message.text,
            intent=intent.value,
            priority=priority,
            assigned_team=assign_team(intent.value),
            approval_status="pending" if requires_approval(intent.value) else "not_required",
            escalation_reason=escalation_reason,
            sla_due_at=datetime.now(timezone.utc) + timedelta(hours=sla_hours(priority.value)),
            metadata={"channel": message.channel.value, "provider": message.provider},
        )
        self.repository.create_ticket(ticket)
        self.repository.add_ticket_event(
            ticket.ticket_id,
            "ticket_created",
            "orchestration",
            {"intent": intent.value, "priority": priority.value, "escalation_reason": escalation_reason},
        )
        return self.sync_ticket(ticket.ticket_id, customer=customer)

    def sync_ticket(self, ticket_id: str, customer: dict | None = None) -> Ticket:
        ticket = self._ticket(ticket_id)
        result = self.crm.create_ticket(ticket, customer)
        updates = {
            "crm_sync_status": result.status,
            "crm_sync_error": result.error,
        }
        if result.status == "synced":
            updates["external_ticket_id"] = result.data.get("external_ticket_id")
            updates["external_ticket_url"] = result.data.get("external_ticket_url")
        updated = self.repository.update_ticket(ticket_id, **updates)
        self.repository.add_ticket_event(
            ticket_id,
            "crm_sync_" + result.status,
            "crm_integration",
            {"error": result.error, **result.data},
        )
        self._audit(ticket, "ticket_crm_sync_" + result.status, {"error": result.error, **result.data})
        return Ticket(**updated)

    def add_comment(self, ticket_id: str, comment: str, actor: str = "admin") -> dict:
        ticket = self._ticket(ticket_id)
        result = (
            self.crm.add_comment(ticket.external_ticket_id, comment)
            if ticket.external_ticket_id
            else None
        )
        details = {
            "comment": comment,
            "crm_sync_status": result.status if result else "local_only",
            "crm_sync_error": result.error if result else None,
        }
        event = self.repository.add_ticket_event(ticket_id, "comment_added", actor, details)
        self._audit(ticket, "ticket_comment_added", details)
        return event

    def update_status(self, ticket_id: str, status: TicketStatus, actor: str = "admin") -> dict:
        ticket = self._ticket(ticket_id)
        result = (
            self.crm.update_ticket_status(ticket.external_ticket_id, status.value)
            if ticket.external_ticket_id
            else None
        )
        updated = self.repository.update_ticket(ticket_id, status=status.value)
        self.repository.add_ticket_event(
            ticket_id,
            "status_updated",
            actor,
            {
                "status": status.value,
                "crm_sync_status": result.status if result else "local_only",
                "crm_sync_error": result.error if result else None,
            },
        )
        self._audit(ticket, "ticket_status_updated", {"status": status.value})
        return updated

    def _ticket(self, ticket_id: str) -> Ticket:
        ticket = self.repository.get_ticket(ticket_id)
        if not ticket:
            raise KeyError(f"Ticket not found: {ticket_id}")
        return Ticket(**ticket)

    def _audit(self, ticket: Ticket, event_type: str, details: dict) -> None:
        self.repository.add_audit_event(
            event_type,
            new_id("corr"),
            customer_id=ticket.customer_id,
            conversation_id=ticket.conversation_id,
            ticket_id=ticket.ticket_id,
            details=details,
        )
