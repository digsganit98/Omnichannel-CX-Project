from __future__ import annotations

from datetime import datetime, timezone

from services.persistence_service.repository import CXRepository
from shared.schemas.agent_assist import ActionType, NBARecommendationSet, NextBestAction
from shared.schemas.tickets import TicketPriority, TicketStatus

_NEGATIVE_STREAK_THRESHOLD = 2
_SLA_NEAR_DUE_FRACTION = 0.25  # flag once <=25% of the SLA window remains


class NextBestActionEngine:
    """Deterministic, rule-based agent-assist recommendations.

    Rules are intentionally deterministic (not LLM-generated) — in a regulated BFSI
    context, a human agent approving/dismissing a suggestion needs a traceable reason,
    not a freeform LLM guess. See shared/schemas/agent_assist.py for the output shape.
    """

    def __init__(self, repository: CXRepository, neo4j_client=None) -> None:
        self.repository = repository
        self.neo4j_client = neo4j_client

    def recommend(self, conversation_id: str, ticket_id: str | None = None, limit: int = 3) -> NBARecommendationSet:
        conversation = self.repository.get_conversation(conversation_id)
        customer_id = (conversation or {}).get("customer_id", "")

        ticket = None
        if ticket_id:
            ticket = self.repository.get_ticket(ticket_id)
        else:
            active = self.repository.find_active_ticket(conversation_id)
            ticket = active.model_dump(mode="json") if active else None

        turns = self.repository.list_recent_turns(conversation_id)

        # Cross-sell/up-sell moved to the opportunity engine (LLM-selected from a
        # code-built candidate set; see opportunity_engine.py) — operational
        # actions only here.
        candidates = [
            self._rule_escalate_aging_high_priority(ticket),
            self._rule_repeat_negative_sentiment(turns),
            self._rule_kyc_pending(ticket),
        ]
        actions = sorted(
            (action for action in candidates if action is not None),
            key=lambda action: action.confidence,
            reverse=True,
        )[:limit]

        return NBARecommendationSet(
            conversation_id=conversation_id,
            customer_id=customer_id,
            ticket_id=ticket.get("ticket_id") if ticket else None,
            actions=actions,
        )

    def _load_graph_context(self, customer_id: str) -> dict:
        """customer_id here is the SQLite CXRepository id (e.g. "cust_82804..."), which is
        NOT the same id space as Neo4j's BFSI graph (e.g. "CRN00010004") — they're generated
        independently. Resolve via the customer's stored channel identities instead of
        assuming the ids coincide (mirrors the priority graph.py._neo4j_customer_id uses)."""
        if not self.neo4j_client or not customer_id:
            return {}
        try:
            from services.neo4j_service.queries import get_customer_context, get_customer_context_by_id
            identifiers = self.repository.list_customer_identifiers(customer_id)
            graph_id = next((i["identifier"] for i in identifiers if i["channel"] == "graph"), None)
            if graph_id:
                return get_customer_context_by_id(self.neo4j_client, graph_id) or {}
            contact = next((i["identifier"] for i in identifiers if i["channel"] in ("whatsapp", "email")), None)
            if contact:
                return get_customer_context(self.neo4j_client, contact) or {}
            return {}
        except Exception:
            return {}

    # ── Rule providers ───────────────────────────────────────────────────

    @staticmethod
    def _rule_escalate_aging_high_priority(ticket: dict | None) -> NextBestAction | None:
        # Only an actively-open ticket has a live SLA that can be breached. Guard with a
        # positive allow-list so any terminal status (resolved, closed, or a future one)
        # never generates an SLA-escalate suggestion.
        active_statuses = {TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value}
        if not ticket or ticket.get("status") not in active_statuses:
            return None
        if ticket.get("priority") not in {TicketPriority.CRITICAL.value, TicketPriority.HIGH.value}:
            return None
        sla_due_at = ticket.get("sla_due_at")
        if not sla_due_at:
            return None
        due = datetime.fromisoformat(sla_due_at)
        created = datetime.fromisoformat(ticket["created_at"])
        now = datetime.now(timezone.utc)
        total_window = (due - created).total_seconds()
        remaining = (due - now).total_seconds()
        if total_window <= 0 or remaining > total_window * _SLA_NEAR_DUE_FRACTION:
            return None
        overdue = remaining < 0
        return NextBestAction(
            action_type=ActionType.ESCALATE_TO_SENIOR,
            reason=(
                f"Ticket {ticket['ticket_id']} is {'past' if overdue else 'nearing'} its "
                f"{ticket['priority']} priority SLA deadline."
            ),
            confidence=0.95 if overdue else 0.8,
            priority=1,
            metadata={"ticket_id": ticket["ticket_id"], "sla_due_at": sla_due_at},
        )

    @staticmethod
    def _rule_repeat_negative_sentiment(turns: list[dict]) -> NextBestAction | None:
        streak = 0
        for turn in reversed(turns):
            if turn.get("direction") != "inbound":
                continue
            if (turn.get("metadata") or {}).get("sentiment") == "negative":
                streak += 1
                if streak >= _NEGATIVE_STREAK_THRESHOLD:
                    return NextBestAction(
                        action_type=ActionType.OFFER_RETENTION,
                        reason=f"Customer has sent {streak} consecutive negative-sentiment messages.",
                        confidence=0.7,
                        priority=2,
                        metadata={"negative_streak": streak},
                    )
            else:
                break
        return None

    @staticmethod
    def _rule_kyc_pending(ticket: dict | None) -> NextBestAction | None:
        if not ticket or ticket.get("intent") != "kyc_update":
            return None
        if ticket.get("status") == TicketStatus.RESOLVED.value:
            return None
        return NextBestAction(
            action_type=ActionType.REQUEST_DOCUMENT,
            reason="Open KYC update request — request the outstanding document from the customer.",
            confidence=0.6,
            priority=3,
            metadata={"ticket_id": ticket["ticket_id"]},
        )

    # NOTE: the old _rule_cross_sell (loan + no life cover) moved into
    # opportunity_engine.build_candidates — cross-sell/up-sell is now LLM-selected
    # from a code-built candidate set and surfaced in the Opportunities card.
