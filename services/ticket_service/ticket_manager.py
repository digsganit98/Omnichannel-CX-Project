from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

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
        ticket_scope = _ticket_scope(intent.value, message.text, escalation_reason)
        existing = (
            self.repository.find_active_ticket_for_scope(conversation_id, intent.value, ticket_scope)
            if ticket_scope
            else self.repository.find_active_ticket_for_intent(conversation_id, intent.value)
        )
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
            metadata={
                "channel": message.channel.value,
                "provider": message.provider,
                "ticket_scope": ticket_scope,
            },
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


def _ticket_scope(intent: str, text: str, escalation_reason: str | None) -> str | None:
    """Keep active L3/L2 tickets from merging unrelated incidents under one broad intent."""
    if not escalation_reason:
        return None
    lowered = text.lower()
    tokens = set(re.findall(r"[a-z0-9]+", lowered))

    def has(*terms: str) -> bool:
        return any(term in lowered for term in terms)

    if intent == Intent.FRAUD_REPORT.value:
        if has("phishing", "phishing link", "entered my banking details", "shared otp", "shared my otp"):
            return "fraud_report:phishing_credential_compromise"
        if has("cannot access", "can't access", "locked out", "login blocked", "password changed"):
            return "fraud_report:account_access_compromise"
        if has("transferred money", "money transferred", "stole money", "money stolen", "funds stolen"):
            return "fraud_report:account_takeover_funds_stolen"
        if has("upi", "debit", "withdrawal", "transaction", "charge"):
            return "fraud_report:unauthorized_transaction"
        if tokens.intersection({"hack", "hacked", "fraud", "scam"}):
            return "fraud_report:account_takeover"
        return "fraud_report:other"

    if intent == Intent.TRANSACTION_DISPUTE.value:
        if has("upi"):
            return "transaction_dispute:upi"
        if has("card", "credit card", "debit card"):
            return "transaction_dispute:card"
        return "transaction_dispute:other"

    if intent == Intent.LOAN_DEFAULT_NOTICE.value:
        return "loan_default_notice:paid_emi_dispute" if has("paid", "already paid") else "loan_default_notice:default"

    if intent == Intent.CARD_MANAGEMENT.value:
        if has("lost", "stolen"):
            return "card_management:lost_or_stolen"
        if has("block", "blocked"):
            return "card_management:block_or_unblock"
        return "card_management:other"

    if intent in {Intent.INSURANCE_CLAIM.value, Intent.CLAIM_STATUS.value}:
        if has("hospital", "hospitalisation", "hospitalization", "medical"):
            return f"{intent}:health_claim"
        if has("accident"):
            return f"{intent}:accident_claim"
        return f"{intent}:other"

    if intent == Intent.KYC_UPDATE.value:
        if has("aadhaar", "aadhar"):
            return "kyc_update:aadhaar"
        if has("pan"):
            return "kyc_update:pan"
        if has("address"):
            return "kyc_update:address"
        return "kyc_update:other"

    return f"{intent}:manual_review"
