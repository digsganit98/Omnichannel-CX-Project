import logging
import time
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from services.agent_service.cx_agent import CXAgent
from services.agent_service.orchestration_agents import (
    IntentDetectionAgent,
    QueryResolutionAgent,
    TicketAction,
    TicketManagementAgent,
    WorkflowAutomationAgent,
)
from services.channel_service.delivery import OutboundDeliveryService
from services.crm_service.client import CRMClient
from services.orchestration_service.state import OrchestrationState, WorkflowStep
from services.persistence_service.repository import CXRepository
from services.rag_service.rag_pipeline import RAGPipeline
from services.ticket_service.ticket_manager import TicketManager
from shared.schemas.messages import InboundMessage
from shared.schemas.responses import ChannelResponse

logger = logging.getLogger(__name__)

ORCHESTRATION_ENGINE = "langgraph_state_graph"
WORKFLOW_EDGES = [
    ("__start__", "receive_message"),
    ("receive_message", "resolve_identity"),
    ("resolve_identity", "load_conversation_context"),
    ("load_conversation_context", "detect_ticket_action"),
    ("detect_ticket_action", "resolve_ticket | classify_intent"),
    ("resolve_ticket", "send_outbound_reply"),
    ("classify_intent", "retrieve_knowledge"),
    ("retrieve_knowledge", "decide_resolution"),
    ("decide_resolution", "create_or_update_ticket | continue_without_ticket"),
    ("create_or_update_ticket", "send_outbound_reply"),
    ("continue_without_ticket", "send_outbound_reply"),
    ("send_outbound_reply", "persist_audit_events"),
    ("persist_audit_events", "__end__"),
]


class GraphState(TypedDict):
    runtime: OrchestrationState


class OrchestrationGraph:
    """LangGraph workflow coordinating the customer support AI agents."""

    def __init__(
        self,
        repository: CXRepository,
        agent: CXAgent | None = None,
        rag: RAGPipeline | None = None,
        delivery: OutboundDeliveryService | None = None,
        crm: CRMClient | None = None,
    ) -> None:
        self.repository = repository
        self.crm = crm or CRMClient()
        self.tickets = TicketManager(repository, self.crm)
        self.intent_agent = IntentDetectionAgent(agent)
        self.query_resolution_agent = QueryResolutionAgent(rag)
        self.ticket_management_agent = TicketManagementAgent(self.tickets)
        self.workflow_automation_agent = WorkflowAutomationAgent(delivery)
        self.workflow = self._build_workflow()

    def run(self, message: InboundMessage) -> ChannelResponse:
        started = time.perf_counter()
        state = OrchestrationState(
            message=message,
            message_id=message.external_message_id or message.correlation_id,
        )
        if not self.repository.reserve_message(message.provider, state.message_id):
            cached = self.repository.get_idempotent_response(message.provider, state.message_id)
            if cached:
                return ChannelResponse(**{**cached, "duplicate": True})
            raise RuntimeError("Duplicate message is still being processed")

        try:
            result = self.workflow.invoke({"runtime": state})
            state = result["runtime"]
            response = self._response(state)
            self.repository.save_idempotent_response(message.provider, state.message_id, response.model_dump())
            logger.info(
                "message_processed",
                extra={
                    **self._common(state),
                    "intent": response.intent,
                    "ticket_id": response.ticket_id,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            return response
        except Exception as exc:
            logger.exception(
                "orchestration_failed",
                extra={**self._common(state), "error": str(exc)},
            )
            try:
                self._audit("workflow_failed", state, details={"error": str(exc)})
            except Exception:
                logger.exception("workflow_failure_audit_failed", extra=self._common(state))
            raise

    def _build_workflow(self):
        workflow = StateGraph(GraphState)
        workflow.add_node("receive_message", self._receive_message)
        workflow.add_node("resolve_identity", self._resolve_identity)
        workflow.add_node("load_conversation_context", self._load_context)
        workflow.add_node("detect_ticket_action", self._detect_ticket_action)
        workflow.add_node("resolve_ticket", self._resolve_ticket)
        workflow.add_node("classify_intent", self._classify_intent)
        workflow.add_node("retrieve_knowledge", self._retrieve_knowledge)
        workflow.add_node("decide_resolution", self._decide_resolution)
        workflow.add_node("create_or_update_ticket", self._create_or_update_ticket)
        workflow.add_node("continue_without_ticket", self._continue_without_ticket)
        workflow.add_node("send_outbound_reply", self._generate_and_send_reply)
        workflow.add_node("persist_audit_events", self._persist_result)
        workflow.add_edge(START, "receive_message")
        workflow.add_edge("receive_message", "resolve_identity")
        workflow.add_edge("resolve_identity", "load_conversation_context")
        workflow.add_edge("load_conversation_context", "detect_ticket_action")
        workflow.add_conditional_edges(
            "detect_ticket_action",
            self._route_ticket_action,
            {
                "resolve_ticket": "resolve_ticket",
                "classify_intent": "classify_intent",
            },
        )
        workflow.add_edge("resolve_ticket", "send_outbound_reply")
        workflow.add_edge("classify_intent", "retrieve_knowledge")
        workflow.add_edge("retrieve_knowledge", "decide_resolution")
        workflow.add_conditional_edges(
            "decide_resolution",
            self._route_ticket_decision,
            {
                "ticket_required": "create_or_update_ticket",
                "answer_directly": "continue_without_ticket",
            },
        )
        workflow.add_edge("create_or_update_ticket", "send_outbound_reply")
        workflow.add_edge("continue_without_ticket", "send_outbound_reply")
        workflow.add_edge("send_outbound_reply", "persist_audit_events")
        workflow.add_edge("persist_audit_events", END)
        return workflow.compile()

    def _receive_message(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        self._complete(state, WorkflowStep.RECEIVE_MESSAGE, "langgraph", provider=state.message.provider)
        return {"runtime": state}

    def _detect_ticket_action(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        state.ticket_action = self.ticket_management_agent.detect_action(state.message, state.context)
        self._complete(
            state,
            WorkflowStep.DETECT_TICKET_ACTION,
            self.ticket_management_agent.name,
            action=state.ticket_action.action.value,
            reason=state.ticket_action.reason,
        )
        return {"runtime": state}

    @staticmethod
    def _route_ticket_action(graph_state: GraphState) -> Literal["resolve_ticket", "classify_intent"]:
        action = graph_state["runtime"].ticket_action.action
        return "resolve_ticket" if action == TicketAction.RESOLVE else "classify_intent"

    def _resolve_ticket(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        active_ticket = state.context["active_ticket"]
        state.ticket = self.ticket_management_agent.resolve_ticket(active_ticket["ticket_id"])
        state.answer = (
            f"Your support ticket {state.ticket.ticket_id} has been marked as resolved. "
            "Thank you for confirming."
        )
        self._audit(
            "ticket_resolved_by_customer",
            state,
            ticket_id=state.ticket.ticket_id,
            details={"reason": state.ticket_action.reason},
        )
        self._complete(
            state,
            WorkflowStep.RESOLVE_TICKET,
            self.ticket_management_agent.name,
            ticket_id=state.ticket.ticket_id,
            status=state.ticket.status.value,
        )
        return {"runtime": state}

    def _resolve_identity(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        message = state.message
        crm_profile = self.crm.lookup_customer(message.channel.value, message.channel_identifier)
        if crm_profile.status == "synced":
            message.profile_metadata["crm"] = crm_profile.data
            message.metadata["crm_customer_id"] = crm_profile.data.get("customer_id") or crm_profile.data.get("id")
        state.customer = self.repository.resolve_customer(message)
        state.conversation = self.repository.get_or_create_conversation(state.customer_id)
        self._audit("inbound_received", state, details={"provider": message.provider})
        if crm_profile.status != "not_configured":
            self._audit(
                "crm_profile_lookup_" + crm_profile.status,
                state,
                details={"error": crm_profile.error, **crm_profile.data},
            )
        self.repository.append_turn(
            conversation_id=state.conversation_id,
            customer_id=state.customer_id,
            channel=message.channel.value,
            direction="inbound",
            text=message.text,
            external_message_id=message.external_message_id,
            subject=message.subject,
            metadata=message.metadata,
        )
        self._complete(
            state,
            WorkflowStep.RESOLVE_IDENTITY,
            "identity_resolution",
            crm_profile_status=crm_profile.status,
        )
        return {"runtime": state}

    def _load_context(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        active_ticket = self.repository.find_active_ticket(state.conversation_id)
        state.context = {
            "conversation_summary": state.conversation.get("summary", ""),
            "recent_turns": self.repository.list_recent_turns(state.conversation_id),
            "customer_metadata": state.customer.get("metadata", {}),
            "active_ticket": active_ticket.model_dump(mode="json") if active_ticket else None,
        }
        self._complete(
            state,
            WorkflowStep.LOAD_CONVERSATION_CONTEXT,
            "workflow_automation_agent",
            recent_turn_count=len(state.context["recent_turns"]),
            active_ticket_id=active_ticket.ticket_id if active_ticket else None,
        )
        return {"runtime": state}

    def _classify_intent(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        state.analysis = self.intent_agent.run(state.message, state.context)
        self._audit(
            "intent_classified",
            state,
            intent=state.analysis.intent.value,
            details=state.analysis.model_dump(),
        )
        self._complete(
            state,
            WorkflowStep.CLASSIFY_INTENT,
            self.intent_agent.name,
            intent=state.analysis.intent.value,
            confidence=state.analysis.confidence,
            urgency=state.analysis.urgency.value,
            source=state.analysis.analysis_source,
        )
        return {"runtime": state}

    def _retrieve_knowledge(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        state.resolution = self.query_resolution_agent.run(state.message, state.context)
        self._audit(
            "retrieval_performed",
            state,
            intent=state.analysis.intent.value,
            details={
                "confidence": state.resolution.confidence,
                "citations": state.resolution.citations,
                "retrieval_backend": state.resolution.retrieval_backend,
                "retrieval_error": state.resolution.retrieval_error,
            },
        )
        self._complete(
            state,
            WorkflowStep.RETRIEVE_KNOWLEDGE,
            self.query_resolution_agent.name,
            confidence=state.resolution.confidence,
            citation_count=len(state.resolution.citations),
            retrieval_backend=state.resolution.retrieval_backend,
        )
        return {"runtime": state}

    def _decide_resolution(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        state.ticket_decision = self.ticket_management_agent.decide(state.analysis, state.resolution)
        self._complete(
            state,
            WorkflowStep.DECIDE_RESOLUTION,
            self.ticket_management_agent.name,
            ticket_required=state.ticket_decision.required,
            reason=state.ticket_decision.reason,
        )
        return {"runtime": state}

    @staticmethod
    def _route_ticket_decision(graph_state: GraphState) -> Literal["ticket_required", "answer_directly"]:
        return "ticket_required" if graph_state["runtime"].ticket_decision.required else "answer_directly"

    def _create_or_update_ticket(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        if state.ticket_decision.required:
            state.ticket = self.ticket_management_agent.create_or_get(
                state.conversation_id,
                state.customer_id,
                state.message,
                state.analysis,
                state.ticket_decision,
                state.customer,
            )
            self._audit(
                "ticket_created",
                state,
                intent=state.analysis.intent.value,
                ticket_id=state.ticket.ticket_id,
            )
            self._audit(
                "ticket_crm_sync_" + state.ticket.crm_sync_status,
                state,
                intent=state.analysis.intent.value,
                ticket_id=state.ticket.ticket_id,
                details={
                    "external_ticket_id": state.ticket.external_ticket_id,
                    "external_ticket_url": state.ticket.external_ticket_url,
                    "error": state.ticket.crm_sync_error,
                },
            )
        self._complete(
            state,
            WorkflowStep.CREATE_OR_UPDATE_TICKET,
            self.ticket_management_agent.name,
            ticket_id=state.ticket.ticket_id if state.ticket else None,
        )
        return {"runtime": state}

    def _continue_without_ticket(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        self._complete(
            state,
            WorkflowStep.CREATE_OR_UPDATE_TICKET,
            self.ticket_management_agent.name,
            skipped=True,
            reason="ticket_not_required",
        )
        return {"runtime": state}

    def _generate_and_send_reply(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        if not state.answer:
            state.answer = self.workflow_automation_agent.compose_answer(state.resolution, state.ticket)
        self._audit(
            "answer_generated",
            state,
            intent=self._intent(state),
            ticket_id=state.ticket.ticket_id if state.ticket else None,
        )
        state.delivery = self.workflow_automation_agent.send_reply(state.message, state.answer)
        self._audit(
            "outbound_sent" if state.delivery["status"] == "sent" else "outbound_failed",
            state,
            intent=self._intent(state),
            ticket_id=state.ticket.ticket_id if state.ticket else None,
            details=state.delivery,
        )
        self._complete(
            state,
            WorkflowStep.SEND_OUTBOUND_REPLY,
            self.workflow_automation_agent.name,
            delivery_status=state.delivery["status"],
        )
        return {"runtime": state}

    def _persist_result(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        provider_message_id = self._provider_message_id(state.delivery)
        outbound_turn = self.repository.append_turn(
            conversation_id=state.conversation_id,
            customer_id=state.customer_id,
            channel=state.message.channel.value,
            direction="outbound",
            text=state.answer,
            intent=self._intent(state),
            urgency=state.analysis.urgency.value if state.analysis else "low",
            resolved=self._resolved(state),
            ticket_id=state.ticket.ticket_id if state.ticket else None,
            external_message_id=provider_message_id,
            delivery_status=state.delivery["status"],
            metadata={
                "citations": state.resolution.citations if state.resolution else [],
                "provider_message_id": provider_message_id,
                "provider_response": state.delivery.get("provider_response"),
            },
        )
        if state.resolution:
            self.repository.add_retrieval_evidence(outbound_turn["turn_id"], state.resolution.contexts)
        self.repository.update_conversation_summary(state.conversation_id, self._summary(state.conversation_id))
        self._complete(
            state,
            WorkflowStep.PERSIST_AUDIT_EVENTS,
            "workflow_automation_agent",
            outbound_turn_id=outbound_turn["turn_id"],
        )
        self._audit(
            "workflow_completed",
            state,
            intent=self._intent(state),
            ticket_id=state.ticket.ticket_id if state.ticket else None,
            details={"steps": [entry.step.value for entry in state.workflow_trace]},
        )
        return {"runtime": state}

    def _response(self, state: OrchestrationState) -> ChannelResponse:
        return ChannelResponse(
            correlation_id=state.message.correlation_id,
            conversation_id=state.conversation_id,
            customer_id=state.customer_id,
            message=state.answer,
            resolved=self._resolved(state),
            intent=self._intent(state),
            sentiment=state.analysis.sentiment if state.analysis else "positive",
            urgency=state.analysis.urgency.value if state.analysis else "low",
            confidence=state.resolution.confidence if state.resolution else 1.0,
            ticket_id=state.ticket.ticket_id if state.ticket else None,
            next_best_action="ticket_closed" if state.ticket_action.action == TicketAction.RESOLVE else (
                "human_follow_up" if state.ticket else "answer_delivered"
            ),
            analysis_source=state.analysis.analysis_source if state.analysis else "operational_command",
            rag_contexts=state.resolution.contexts if state.resolution else [],
            citations=state.resolution.citations if state.resolution else [],
            retrieval_backend=state.resolution.retrieval_backend if state.resolution else "not_required",
            llm_model=state.resolution.llm.get("model") if state.resolution else None,
            llm_used=state.resolution.llm.get("llm_used", False) if state.resolution else False,
            outbound_status=state.delivery["status"],
            outbound_error=state.delivery.get("error"),
            workflow_trace=[entry.model_dump(mode="json") for entry in state.workflow_trace],
        )

    @staticmethod
    def _provider_message_id(delivery: dict) -> str | None:
        provider_response = delivery.get("provider_response") or {}
        messages = provider_response.get("messages") or []
        if messages and isinstance(messages[0], dict):
            return messages[0].get("id")
        return None

    def _complete(self, state: OrchestrationState, step: WorkflowStep, agent: str, **details) -> None:
        state.complete(step, agent, **details)
        self._audit(
            "workflow_step_completed",
            state,
            details={"step": step.value, "agent": agent, **details},
        )

    def _summary(self, conversation_id: str) -> str:
        recent = self.repository.list_recent_turns(conversation_id, limit=6)
        return " | ".join(f"{turn['direction']}: {turn['text'][:120]}" for turn in recent)

    def _common(self, state: OrchestrationState) -> dict:
        return {
            "correlation_id": state.message.correlation_id,
            "customer_id": state.customer_id,
            "conversation_id": state.conversation_id,
            "message_id": state.message_id,
            "channel": state.message.channel.value,
        }

    @staticmethod
    def _intent(state: OrchestrationState) -> str:
        if state.ticket_action.action == TicketAction.RESOLVE:
            return "ticket_resolution"
        return state.analysis.intent.value

    @staticmethod
    def _resolved(state: OrchestrationState) -> bool:
        if state.ticket_action.action == TicketAction.RESOLVE:
            return True
        return not state.ticket_decision.required

    def _audit(self, event_type: str, state: OrchestrationState, **values) -> None:
        self.repository.add_audit_event(event_type, **self._common(state), **values)
