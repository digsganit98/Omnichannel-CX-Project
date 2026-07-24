from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from services.crm_service.client import CRMClient
from services.persistence_service.repository import CXRepository
from services.pii_service.masker import mask_text
from services.ticket_service.assignment import assign_team
from services.ticket_service.priority_scoring import score_priority
from services.workflow_service.approvals import requires_approval
from services.workflow_service.sla import sla_hours
from shared.schemas.intents import Intent, Urgency
from shared.schemas.messages import InboundMessage
from shared.schemas.tickets import Ticket, TicketStatus
from shared.utils.ids import new_id


class TicketManager:
    def __init__(self, repository: CXRepository, crm: CRMClient | None = None, generator=None) -> None:
        self.repository = repository
        self.crm = crm or CRMClient()
        # Optional LLM used only by the tier-4 ticket referee (_referee_match).
        # Deliberately no default instance: without a generator the referee is
        # skipped and unmatched messages open a new ticket (pre-referee behavior).
        self.generator = generator

    def create_or_get_ticket(
        self,
        conversation_id: str,
        customer_id: str,
        message: InboundMessage,
        intent: Intent,
        urgency: Urgency,
        escalation_reason: str | None = None,
        customer: dict | None = None,
        sentiment: str = "neutral",
        graph_context: dict | None = None,
    ) -> Ticket:
        ticket_scope = _ticket_scope(intent.value, message.text, escalation_reason)
        existing = (
            self.repository.find_active_ticket_for_scope(conversation_id, intent.value, ticket_scope)
            if ticket_scope
            else self.repository.find_active_ticket_for_intent(conversation_id, intent.value)
        )
        if not existing and ticket_scope and ticket_scope != f"{intent.value}:other":
            # Omnichannel continuation: a vague opener ("dispute a transaction") gets the
            # ":other" fallback scope; when the customer then supplies specifics ("on my
            # Mastercard"), the specific scope must REFINE that open ticket, not fork a
            # duplicate. Only ":other" is upgraded — two specific scopes (card vs upi)
            # are genuinely distinct incidents and still get separate tickets.
            fallback = self.repository.find_active_ticket_for_scope(
                conversation_id, intent.value, f"{intent.value}:other"
            )
            if fallback:
                existing = self._refine_ticket_scope(fallback, ticket_scope, message)
        if not existing and ticket_scope:
            # Tier-4 omnichannel referee: the scope label didn't string-match any
            # active ticket (e.g. a vague "any update on my dispute?" follow-up
            # arriving on another channel after the ticket was refined to :card).
            # Labels can't answer "same matter or new matter?" — ask the LLM to
            # pick among the CODE-VETTED candidates (active, same intent, same
            # conversation) or say NEW. Any doubt/error/absent-LLM ⇒ new ticket:
            # a spurious fork is visible and fixable; a spurious merge corrupts
            # the record silently.
            candidates = self.repository.list_active_tickets_for_intent(conversation_id, intent.value)
            if candidates:
                existing = self._referee_match(candidates, message)
        if existing:
            return existing
        priority, breakdown = score_priority(intent, urgency, sentiment, graph_context)
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
            priority_score=breakdown.total,
            priority_breakdown=breakdown.model_dump(),
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

    def _refine_ticket_scope(self, ticket: Ticket, new_scope: str, message: InboundMessage) -> Ticket:
        """Upgrade an ':other'-scoped ticket to a specific scope when details arrive (any channel)."""
        metadata = {**ticket.metadata, "ticket_scope": new_scope}
        # Append the newly-supplied details to the ticket description. The original
        # description is frozen at the vague opener ("please help with a dispute");
        # without this, the ticket's own text never mentions the specifics that
        # arrived later (merchant/amount), leaving the referee and the admin UI
        # matching against a summary that omits its own defining facts.
        detail = (message.text or "").strip()
        new_desc = ticket.description
        if detail and detail not in (ticket.description or ""):
            new_desc = f"{ticket.description}\n[Details added: {detail[:500]}]"
        updated = self.repository.update_ticket(
            ticket.ticket_id, metadata_json=json.dumps(metadata), description=new_desc
        )
        details = {
            "previous_scope": ticket.metadata.get("ticket_scope"),
            "new_scope": new_scope,
            "channel": message.channel.value,
            "detail_text": message.text[:500],
        }
        self.repository.add_ticket_event(ticket.ticket_id, "ticket_scope_refined", "orchestration", details)
        self._audit(ticket, "ticket_scope_refined", details)
        return Ticket(**updated)

    def _referee_match(self, candidates: list[Ticket], message: InboundMessage) -> Ticket | None:
        """Ask the LLM whether an unmatched message refers to an open ticket or a new matter.

        The LLM only ever picks from the code-vetted candidate list; any other
        answer, a parse miss, an LLM failure, or no generator at all returns
        None (=> caller opens a new ticket — the safe default).
        """
        if not self.generator:
            return None
        by_id = {t.ticket_id: t for t in candidates}
        try:
            masked_text, _ = mask_text(message.text)
            lines = []
            for i, t in enumerate(by_id.values(), 1):
                masked_desc, _ = mask_text((t.description or "")[:300])
                opened = t.created_at.strftime("%d %b %Y") if t.created_at else "unknown date"
                subtype = _scope_label(t.metadata.get("ticket_scope"), t.intent)
                lines.append(f'{i}. {t.ticket_id} — {subtype} (opened {opened}): "{masked_desc}"')
            result = self.generator._generate(
                system_prompt=(
                    "You decide whether a customer's new message is a follow-up to one of their "
                    "existing open support tickets, or a brand-new separate matter.\n"
                    "Answer with a ticket id ONLY when the message clearly continues that same "
                    "specific matter — e.g. asking for its status/update, adding details to it, or "
                    "referring to the same transaction, merchant, account, or amount already in that "
                    "ticket (possibly from a different channel).\n"
                    "Answer NEW when the message describes a DIFFERENT transaction, merchant, "
                    "account, or amount than any open ticket — even if it is the same general kind "
                    "of issue (e.g. another dispute about a different charge is NEW, not a follow-up).\n"
                    "When unsure, answer NEW. Reply with exactly one ticket id from the list, or the "
                    "word NEW — no other words."
                ),
                user_prompt=(
                    "Open tickets for this customer's conversation (each shown as: id — subtype "
                    "(opened date): description). The subtype (e.g. 'card', 'upi') identifies which "
                    "specific matter the ticket is about — use it to match:\n"
                    + "\n".join(lines)
                    + "\n\nExamples:\n"
                    '- "Any update on my dispute? This is urgent." -> the matching ticket id '
                    "(a status follow-up on the existing matter)\n"
                    '- "What about the card charge at TechMart?" -> the ticket whose subtype is the '
                    "card dispute (refers to that same matter)\n"
                    '- "I want to dispute another charge - my gym billed me twice this month." -> '
                    "NEW (a different merchant/charge, so a separate matter)\n\n"
                    f'New customer message: "{masked_text}"\n\n'
                    "Answer with exactly the ticket id it continues, or NEW."
                ),
                operation="ticket_referee",
            )
            if not result.get("llm_used"):
                return None
            answer = (result.get("text") or "").strip()
            # Exact-membership validation: accept only a vetted candidate id.
            matched = next((tid for tid in by_id if tid.lower() in answer.lower()), None)
            if not matched:
                return None
            ticket = by_id[matched]
            details = {
                "matched_ticket": matched,
                "candidate_ids": list(by_id),
                "channel": message.channel.value,
                "detail_text": message.text[:200],
            }
            self.repository.add_ticket_event(matched, "ticket_referee_attached", "orchestration", details)
            self._audit(ticket, "ticket_referee_attached", details)
            return ticket
        except Exception:
            return None

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


def _scope_label(ticket_scope: str | None, intent: str) -> str:
    """Human-readable subtype for the referee prompt, derived from the scope tag.

    'transaction_dispute:card' -> 'card transaction dispute'. The scope subtype is
    the reliable discriminator between same-intent tickets (card vs upi), so it is
    surfaced prominently rather than left as a raw tag the model may ignore.
    """
    base = (intent or "ticket").replace("_", " ")
    if not ticket_scope or ":" not in ticket_scope:
        return base
    subtype = ticket_scope.split(":", 1)[1].replace("_", " ")
    if subtype in ("other", "manual review"):
        return base
    return f"{subtype} {base}"


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
