from enum import StrEnum

from pydantic import BaseModel, Field

from services.agent_service.cx_agent import CXAgent
from services.channel_service.delivery import OutboundDeliveryService
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
    """Routes to Neo4j (transactional) or RAG/KB (policy/general) based on intent."""

    name = "query_resolution_agent"

    def __init__(self, rag: RAGPipeline | None = None, neo4j_client=None) -> None:
        self.rag = rag or RAGPipeline()
        self.neo4j_client = neo4j_client

    def run(self, message: InboundMessage, context: dict, intent: str | None = None) -> QueryResolution:
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
                                retrieval_backend="neo4j_graph",
                            )
            except Exception:
                pass
        return QueryResolution(**self.rag.answer(message.text, context))


# ── Agent 3: Ticket Creation ─────────────────────────────────────────────────

class TicketCreationAgent:
    """Decides when a JIRA ticket is needed and creates it."""

    name = "ticket_creation_agent"

    def __init__(self, tickets: TicketManager) -> None:
        self.tickets = tickets

    def decide(self, analysis: IntentResult, resolution: QueryResolution) -> TicketDecision:
        reason = self._escalation_reason(analysis, resolution)
        return TicketDecision(required=reason is not None, reason=reason)

    @staticmethod
    def detect_action(message: InboundMessage, context: dict) -> TicketActionDecision:
        if not context.get("active_ticket"):
            return TicketActionDecision()
        text = message.text.lower()
        has_close_action = any(phrase in text for phrase in ("close", "resolve", "mark as resolved"))
        has_ticket_context = any(phrase in text for phrase in ("ticket", "case", "query", "request"))
        has_resolution_cue = any(phrase in text for phrase in ("resolved", "fixed", "sorted", "thanks", "thank you"))
        if has_close_action and has_ticket_context and has_resolution_cue:
            return TicketActionDecision(action=TicketAction.RESOLVE, reason="customer_confirmed_resolution")
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
    def _escalation_reason(analysis: IntentResult, resolution: QueryResolution) -> str | None:
        if analysis.intent == Intent.HUMAN_ESCALATION:
            return "customer_requested_human"
        if analysis.intent in MANUAL_REVIEW_INTENTS:
            return f"manual_review_required:{analysis.intent.value}"
        if analysis.urgency == Urgency.HIGH:
            return "high_urgency"
        if analysis.confidence < 0.5:
            return "low_intent_confidence"
        if not resolution.contexts and resolution.retrieval_backend != "neo4j_graph":
            return "knowledge_not_found"
        if resolution.confidence < 0.25 and resolution.retrieval_backend != "neo4j_graph":
            return "low_retrieval_confidence"
        return None


# ── Backwards-compatible aliases ─────────────────────────────────────────────
# Old class names kept so existing imports in tests / other modules don't break.
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
        return (
            "I have captured your request and created a support ticket. "
            f"Our {ticket.assigned_team.replace('_', ' ')} team will review it. "
            f"Reference: {ticket.ticket_id}."
        )

    def send_reply(self, message: InboundMessage, answer: str) -> dict:
        return self.delivery.send(message, answer)
