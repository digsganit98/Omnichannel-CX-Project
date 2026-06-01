import logging
import time

from services.agent_service.cx_agent import CXAgent
from services.channel_service.delivery import OutboundDeliveryService
from services.crm_service.client import CRMClient
from services.persistence_service.repository import CXRepository
from services.rag_service.rag_pipeline import RAGPipeline
from services.ticket_service.ticket_manager import TicketManager
from shared.schemas.intents import Intent, IntentResult, Urgency
from shared.schemas.messages import InboundMessage
from shared.schemas.responses import ChannelResponse

logger = logging.getLogger(__name__)

MANUAL_REVIEW_INTENTS = {Intent.REFUND_REQUEST, Intent.RETURN_REQUEST, Intent.COMPLAINT, Intent.HUMAN_ESCALATION}


class OrchestrationGraph:
    def __init__(
        self,
        repository: CXRepository,
        agent: CXAgent | None = None,
        rag: RAGPipeline | None = None,
        delivery: OutboundDeliveryService | None = None,
        crm: CRMClient | None = None,
    ) -> None:
        self.repository = repository
        self.agent = agent or CXAgent()
        self.rag = rag or RAGPipeline()
        self.delivery = delivery or OutboundDeliveryService()
        self.crm = crm or CRMClient()
        self.tickets = TicketManager(repository, self.crm)

    def run(self, message: InboundMessage) -> ChannelResponse:
        started = time.perf_counter()
        message_id = message.external_message_id or message.correlation_id
        if not self.repository.reserve_message(message.provider, message_id):
            cached = self.repository.get_idempotent_response(message.provider, message_id)
            if cached:
                return ChannelResponse(**{**cached, "duplicate": True})
            raise RuntimeError("Duplicate message is still being processed")

        crm_profile = self.crm.lookup_customer(message.channel.value, message.channel_identifier)
        if crm_profile.status == "synced":
            message.profile_metadata["crm"] = crm_profile.data
            message.metadata["crm_customer_id"] = crm_profile.data.get("customer_id") or crm_profile.data.get("id")
        customer = self.repository.resolve_customer(message)
        customer_id = customer["customer_id"]
        conversation = self.repository.get_or_create_conversation(customer_id)
        conversation_id = conversation["conversation_id"]
        common = {
            "correlation_id": message.correlation_id,
            "customer_id": customer_id,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "channel": message.channel.value,
        }
        self._audit("inbound_received", common, details={"provider": message.provider})
        if crm_profile.status != "not_configured":
            self._audit(
                "crm_profile_lookup_" + crm_profile.status,
                common,
                details={"error": crm_profile.error, **crm_profile.data},
            )
        inbound_turn = self.repository.append_turn(
            conversation_id=conversation_id,
            customer_id=customer_id,
            channel=message.channel.value,
            direction="inbound",
            text=message.text,
            external_message_id=message.external_message_id,
            subject=message.subject,
            metadata=message.metadata,
        )
        context = self._load_context(conversation, customer, conversation_id)
        analysis = self.agent.analyze(message.text, context)
        self._audit("intent_classified", common, intent=analysis.intent.value, details=analysis.model_dump())

        rag_result = self.rag.answer(message.text, context)
        self._audit(
            "retrieval_performed", common, intent=analysis.intent.value,
            details={"confidence": rag_result["confidence"], "citations": rag_result["citations"]},
        )
        should_ticket = self._requires_ticket(analysis, rag_result)
        ticket = None
        if should_ticket:
            ticket = self.tickets.create_or_get_ticket(
                conversation_id,
                customer_id,
                message,
                analysis.intent,
                analysis.urgency,
                escalation_reason=self._escalation_reason(analysis, rag_result),
                customer=customer,
            )
            answer = (
                "I have captured your request and created a support ticket. "
                f"Our {ticket.assigned_team.replace('_', ' ')} team will review it. "
                f"Reference: {ticket.ticket_id}."
            )
            self._audit("ticket_created", common, intent=analysis.intent.value, ticket_id=ticket.ticket_id)
            self._audit(
                "ticket_crm_sync_" + ticket.crm_sync_status,
                common,
                intent=analysis.intent.value,
                ticket_id=ticket.ticket_id,
                details={
                    "external_ticket_id": ticket.external_ticket_id,
                    "external_ticket_url": ticket.external_ticket_url,
                    "error": ticket.crm_sync_error,
                },
            )
        else:
            answer = rag_result["answer"]
        self._audit("answer_generated", common, intent=analysis.intent.value, ticket_id=ticket.ticket_id if ticket else None)

        delivery = self.delivery.send(message, answer)
        delivery_event = "outbound_sent" if delivery["status"] == "sent" else "outbound_failed"
        self._audit(
            delivery_event, common, intent=analysis.intent.value, ticket_id=ticket.ticket_id if ticket else None,
            details=delivery,
        )
        outbound_turn = self.repository.append_turn(
            conversation_id=conversation_id,
            customer_id=customer_id,
            channel=message.channel.value,
            direction="outbound",
            text=answer,
            intent=analysis.intent.value,
            urgency=analysis.urgency.value,
            resolved=not should_ticket,
            ticket_id=ticket.ticket_id if ticket else None,
            delivery_status=delivery["status"],
            metadata={"citations": rag_result["citations"]},
        )
        self.repository.add_retrieval_evidence(outbound_turn["turn_id"], rag_result["contexts"])
        self.repository.update_conversation_summary(conversation_id, self._summary(conversation_id))

        response = ChannelResponse(
            correlation_id=message.correlation_id,
            conversation_id=conversation_id,
            customer_id=customer_id,
            message=answer,
            resolved=not should_ticket,
            intent=analysis.intent.value,
            sentiment=analysis.sentiment,
            urgency=analysis.urgency.value,
            confidence=rag_result["confidence"],
            ticket_id=ticket.ticket_id if ticket else None,
            analysis_source=analysis.analysis_source,
            rag_contexts=rag_result["contexts"],
            citations=rag_result["citations"],
            llm_model=rag_result["llm"].get("model"),
            llm_used=rag_result["llm"].get("llm_used", False),
            outbound_status=delivery["status"],
        )
        self.repository.save_idempotent_response(message.provider, message_id, response.model_dump())
        logger.info("message_processed", extra={**common, "intent": response.intent, "ticket_id": response.ticket_id,
                                                "latency_ms": round((time.perf_counter() - started) * 1000, 2)})
        return response

    def _load_context(self, conversation: dict, customer: dict, conversation_id: str) -> dict:
        active_ticket = self.repository.find_active_ticket(conversation_id)
        return {
            "conversation_summary": conversation.get("summary", ""),
            "recent_turns": self.repository.list_recent_turns(conversation_id),
            "customer_metadata": customer.get("metadata", {}),
            "active_ticket": active_ticket.model_dump(mode="json") if active_ticket else None,
        }

    @staticmethod
    def _requires_ticket(analysis: IntentResult, rag_result: dict) -> bool:
        return (
            analysis.intent in MANUAL_REVIEW_INTENTS
            or analysis.urgency == Urgency.HIGH
            or analysis.confidence < 0.5
            or rag_result["confidence"] < 0.25
            or not rag_result["contexts"]
        )

    def _summary(self, conversation_id: str) -> str:
        recent = self.repository.list_recent_turns(conversation_id, limit=6)
        return " | ".join(f"{turn['direction']}: {turn['text'][:120]}" for turn in recent)

    @staticmethod
    def _escalation_reason(analysis: IntentResult, rag_result: dict) -> str:
        if analysis.intent == Intent.HUMAN_ESCALATION:
            return "customer_requested_human"
        if analysis.intent in MANUAL_REVIEW_INTENTS:
            return f"manual_review_required:{analysis.intent.value}"
        if analysis.urgency == Urgency.HIGH:
            return "high_urgency"
        if not rag_result["contexts"]:
            return "knowledge_not_found"
        return "low_confidence"

    def _audit(self, event_type: str, common: dict, **values) -> None:
        self.repository.add_audit_event(event_type, **common, **values)
