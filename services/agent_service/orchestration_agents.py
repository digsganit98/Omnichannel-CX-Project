from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from services.agent_service.cx_agent import CXAgent
from services.channel_service.delivery import OutboundDeliveryService
from services.rag_service.groq_generator import GroqGenerator
from services.rag_service.rag_pipeline import RAGPipeline
from services.ticket_service.ticket_manager import TicketManager
from shared.schemas.intents import Intent, IntentResult, Urgency
from shared.schemas.messages import InboundMessage
from shared.schemas.tickets import Ticket, TicketStatus


MANUAL_REVIEW_INTENTS = {
    Intent.FRAUD_REPORT,
    Intent.TRANSACTION_DISPUTE,
    Intent.INSURANCE_CLAIM,
    Intent.LOAN_DEFAULT_NOTICE,
    Intent.COMPLAINT,
    Intent.HUMAN_ESCALATION,
}


class QueryResolution(BaseModel):
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    contexts: list[dict] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    llm: dict = Field(default_factory=dict)
    retrieval_backend: str = "unknown"
    retrieval_error: str | None = None


class TicketDecision(BaseModel):
    required: bool
    reason: str | None = None


class TicketAction(StrEnum):
    NONE = "none"
    RESOLVE = "resolve"


class TicketActionDecision(BaseModel):
    action: TicketAction = TicketAction.NONE
    reason: str | None = None


# ── Agent 1: Intent Classification ──────────────────────────────────────────

class IntentClassificationAgent:
    """Classifies a BFSI message and enriches context with Neo4j customer graph."""

    name = "intent_classification_agent"

    def __init__(self, classifier: CXAgent | None = None, neo4j_client=None) -> None:
        self.classifier = classifier or CXAgent()
        self.neo4j_client = neo4j_client

    def run(self, message: InboundMessage, context: dict) -> IntentResult:
        if self.neo4j_client:
            try:
                from services.neo4j_service.queries import get_customer_context
                graph_ctx = get_customer_context(self.neo4j_client, message.channel_identifier)
                if graph_ctx:
                    context = {**context, "graph_context": graph_ctx}
            except Exception:
                pass
        return self.classifier.analyze(message.text, context)


# ── Agent 2: Query / Complaint Resolution ───────────────────────────────────

class QueryResolutionAgent:
    """Routes to ticket lookup, Neo4j (transactional), or RAG/KB based on intent."""

    name = "query_resolution_agent"

    def __init__(self, rag: RAGPipeline | None = None, neo4j_client=None) -> None:
        self.rag = rag or RAGPipeline()
        self.neo4j_client = neo4j_client

    def run(self, message: InboundMessage, context: dict, intent: str | None = None) -> QueryResolution:
        channel = context.get("channel", "")

        # ── Priority 1: Ticket status lookup (cross-channel memory) ──────────
        if intent == Intent.TICKET_STATUS:
            tickets = context.get("customer_tickets", [])
            if tickets:
                answer = _format_ticket_status(tickets, channel)
                return QueryResolution(
                    answer=answer,
                    confidence=0.98,
                    contexts=[{
                        "text": answer,
                        "score": 0.98,
                        "metadata": {"source": "customer_ticket_lookup", "doc_type": "customer_data"},
                    }],
                    citations=[{"index": 1, "source": "customer_ticket_lookup", "score": 0.98}],
                    retrieval_backend="customer_ticket_lookup",
                )

        # ── Priority 2: Neo4j transactional data (loans, claims, etc.) ───────
        if intent and self.neo4j_client:
            try:
                from services.neo4j_service.queries import neo4j_answer, TRANSACTIONAL_INTENTS
                if intent in TRANSACTIONAL_INTENTS:
                    graph_ctx = context.get("graph_context", {})
                    customer_id = graph_ctx.get("customer_id", "")
                    if customer_id:
                        answer = neo4j_answer(self.neo4j_client, intent, customer_id)
                        if answer:
                            return QueryResolution(
                                answer=answer,
                                confidence=0.95,
                                contexts=[{
                                    "text": answer,
                                    "score": 0.95,
                                    "metadata": {
                                        "source": "neo4j_customer_graph",
                                        "doc_type": "customer_graph",
                                        "retrieval": "neo4j_graph",
                                    },
                                }],
                                citations=[{"index": 1, "source": "neo4j_customer_graph", "score": 0.95}],
                                retrieval_backend="neo4j_graph",
                            )
            except Exception:
                pass

        # ── Priority 3: RAG / Knowledge Base ──────────────────────────────────
        rag_context = {**context, "neo4j_attempted": bool(intent and self.neo4j_client)}
        return QueryResolution(**self.rag.answer(message.text, rag_context))


def _format_ticket_status(tickets: list[dict], channel: str = "") -> str:
    """Format open tickets as a natural-language status response."""
    if not tickets:
        return "I could not find any open support requests for your account."

    if channel == "whatsapp":
        # Brief format for WhatsApp
        lines = [f"Here {'is' if len(tickets) == 1 else 'are'} your open support request(s):"]
        for t in tickets:
            sla = _relative_time(t.get("sla_due_at"))
            lines.append(
                f"• Ref: {t['ticket_id']} | {t['intent'].replace('_', ' ').title()} | "
                f"Status: {t['status'].upper()} | Team: {t['assigned_team'].replace('_', ' ').title()}"
                + (f" | Due: {sla}" if sla else "")
            )
        return "\n".join(lines)
    else:
        # Structured format for email / default
        lines = ["Here is a summary of your open support request(s):\n"]
        for t in tickets:
            sla = _relative_time(t.get("sla_due_at"))
            lines.append(f"Reference: {t['ticket_id']}")
            lines.append(f"Type: {t['intent'].replace('_', ' ').title()}")
            lines.append(f"Status: {t['status'].upper()}")
            lines.append(f"Assigned to: {t['assigned_team'].replace('_', ' ').title()}")
            if sla:
                lines.append(f"Expected resolution: {sla}")
            if t.get("escalation_reason"):
                lines.append(f"Reason for escalation: {t['escalation_reason'].replace('_', ' ')}")
            lines.append("")
        lines.append("Our team is working on your request. We will contact you once there is an update.")
        return "\n".join(lines)


def _relative_time(iso_str: str | None) -> str:
    """Convert ISO timestamp to a human-readable relative time string."""
    if not iso_str:
        return ""
    try:
        due = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = due - now
        hours = int(diff.total_seconds() / 3600)
        if hours < 0:
            return "overdue"
        if hours < 1:
            return "within the hour"
        if hours < 24:
            return f"within {hours} hour(s)"
        return f"within {hours // 24} day(s)"
    except Exception:
        return ""


# ── Agent 3: Ticket Creation ─────────────────────────────────────────────────

class TicketCreationAgent:
    """Decides when a JIRA ticket is needed and creates it."""

    name = "ticket_creation_agent"

    def __init__(self, tickets: TicketManager, generator: GroqGenerator | None = None) -> None:
        self.tickets = tickets
        self.generator = generator or GroqGenerator()

    def decide(self, analysis: IntentResult, resolution: QueryResolution, context: dict | None = None) -> TicketDecision:
        reason = self._escalation_reason(analysis, resolution, context or {})
        return TicketDecision(required=reason is not None, reason=reason)

    def detect_action(self, message: InboundMessage, context: dict) -> TicketActionDecision:
        if not context.get("active_ticket"):
            return TicketActionDecision()

        # Fast keyword check first (no LLM cost for clear cases).
        text = message.text.lower()
        has_close_action = any(phrase in text for phrase in ("close", "resolve", "mark as resolved"))
        has_ticket_context = any(phrase in text for phrase in ("ticket", "case", "query", "request"))
        has_resolution_cue = any(phrase in text for phrase in ("resolved", "fixed", "sorted", "thanks", "thank you"))
        if has_close_action and has_ticket_context and has_resolution_cue:
            return TicketActionDecision(action=TicketAction.RESOLVE, reason="customer_confirmed_resolution")

        # LLM fallback for ambiguous messages (e.g., "All good now", "Issue is sorted").
        try:
            result = self.generator._generate(
                system_prompt="You are a resolution detector. Answer only YES or NO.",
                user_prompt=(
                    f"Customer message: \"{message.text}\"\n"
                    "Does this message indicate that the customer's issue has been resolved "
                    "and they no longer need support? Answer YES or NO only."
                ),
            )
            if result.get("llm_used") and result.get("text", "").strip().upper().startswith("YES"):
                return TicketActionDecision(action=TicketAction.RESOLVE, reason="llm_confirmed_resolution")
        except Exception:
            pass

        return TicketActionDecision()

    def resolve_ticket(self, ticket_id: str) -> Ticket:
        updated = self.tickets.update_status(ticket_id, status=TicketStatus.RESOLVED, actor="customer_message")
        return Ticket(**updated)

    def create_or_get(
        self,
        conversation_id: str,
        customer_id: str,
        message: InboundMessage,
        analysis: IntentResult,
        decision: TicketDecision,
        customer: dict,
    ) -> Ticket:
        return self.tickets.create_or_get_ticket(
            conversation_id,
            customer_id,
            message,
            analysis.intent,
            analysis.urgency,
            escalation_reason=decision.reason,
            customer=customer,
        )

    @staticmethod
    def _escalation_reason(analysis: IntentResult, resolution: QueryResolution, context: dict) -> str | None:
        # Rule 1: Customer explicitly asked for human
        if analysis.intent == Intent.HUMAN_ESCALATION:
            return "customer_requested_human"

        # Rule 2: Intents that always require manual review
        if analysis.intent in MANUAL_REVIEW_INTENTS:
            return f"manual_review_required:{analysis.intent.value}"

        # Rule 3: Ticket status is a lookup — never create a new ticket
        if analysis.intent == Intent.TICKET_STATUS:
            return None

        # Rule 4: High urgency
        if analysis.urgency == Urgency.HIGH:
            return "high_urgency"

        # Rule 5: Low intent confidence (industry threshold: 0.6)
        if analysis.confidence < 0.6:
            return "low_intent_confidence"

        # Rule 6: Repeat customer — has ≥ 3 open tickets (escalate to avoid ticket spam)
        if len(context.get("customer_tickets", [])) >= 3:
            return "repeat_customer_escalation"

        # Rule 7: No knowledge found and not sourced from Neo4j
        if not resolution.contexts and resolution.retrieval_backend != "neo4j_graph":
            return "knowledge_not_found"

        # Rule 8: Very low retrieval confidence (industry threshold: 0.3)
        if resolution.confidence < 0.3 and resolution.retrieval_backend not in (
            "neo4j_graph", "customer_ticket_lookup"
        ):
            return "low_retrieval_confidence"

        return None


# ── Backwards-compatible aliases ─────────────────────────────────────────────
IntentDetectionAgent = IntentClassificationAgent
TicketManagementAgent = TicketCreationAgent


class WorkflowAutomationAgent:
    """Thin wrapper kept for backwards compatibility; logic now lives in graph.py."""

    name = "workflow_automation_agent"

    def __init__(self, delivery: OutboundDeliveryService | None = None) -> None:
        self.delivery = delivery or OutboundDeliveryService()

    @staticmethod
    def compose_answer(resolution: QueryResolution, ticket: Ticket | None) -> str:
        if ticket is None:
            return resolution.answer
        ticket_note = (
            "I have captured your request and created a support ticket. "
            f"Our {ticket.assigned_team.replace('_', ' ')} team will review it. "
            f"Reference: {ticket.ticket_id}."
        )
        if resolution.contexts and resolution.answer:
            return f"{resolution.answer}\n\n{ticket_note}"
        return ticket_note

    def send_reply(self, message: InboundMessage, answer: str) -> dict:
        return self.delivery.send(message, answer)
