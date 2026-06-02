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
    Intent.REFUND_REQUEST,
    Intent.RETURN_REQUEST,
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


class IntentDetectionAgent:
    """Classifies a message with validated LLM output and deterministic fallback rules."""

    name = "intent_detection_agent"

    def __init__(self, classifier: CXAgent | None = None) -> None:
        self.classifier = classifier or CXAgent()

    def run(self, message: InboundMessage, context: dict) -> IntentResult:
        return self.classifier.analyze(message.text, context)


class QueryResolutionAgent:
    """Retrieves verified knowledge and generates a cited customer answer."""

    name = "query_resolution_agent"

    def __init__(self, rag: RAGPipeline | None = None) -> None:
        self.rag = rag or RAGPipeline()

    def run(self, message: InboundMessage, context: dict) -> QueryResolution:
        return QueryResolution(**self.rag.answer(message.text, context))


class TicketManagementAgent:
    """Decides when human review is needed and delegates durable ticket creation."""

    name = "ticket_management_agent"

    def __init__(self, tickets: TicketManager) -> None:
        self.tickets = tickets

    def decide(self, analysis: IntentResult, resolution: QueryResolution) -> TicketDecision:
        reason = self._escalation_reason(analysis, resolution)
        return TicketDecision(required=reason is not None, reason=reason)

    @staticmethod
    def detect_action(message: InboundMessage, context: dict) -> TicketActionDecision:
        """Recognize narrow customer-side ticket commands before running the RAG path."""
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
        if not resolution.contexts:
            return "knowledge_not_found"
        if resolution.confidence < 0.25:
            return "low_retrieval_confidence"
        return None


class WorkflowAutomationAgent:
    """Builds the final action and delivers the answer through the inbound channel."""

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
