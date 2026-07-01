import logging
import time
from datetime import datetime, timezone
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from services.agent_service.cx_agent import CXAgent
from services.agent_service.orchestration_agents import (
    IntentClassificationAgent,
    QueryResolutionAgent,
    TicketAction,
    TicketCreationAgent,
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

try:
    from services.neo4j_service import writer as neo4j_writer
except Exception:
    neo4j_writer = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

ORCHESTRATION_ENGINE = "langgraph_state_graph"

# Human-readable edge map shown in /admin/orchestration/definition
WORKFLOW_EDGES = [
    ("__start__", "receive_message"),
    ("receive_message", "resolve_identity"),
    ("resolve_identity", "load_conversation_context"),
    ("load_conversation_context", "detect_ticket_action"),
    ("detect_ticket_action", "resolve_ticket | classify_intent [Agent 1]"),
    ("resolve_ticket", "send_outbound_reply"),
    ("classify_intent [Agent 1]", "resolve_query [Agent 2]"),
    ("resolve_query [Agent 2]", "decide_ticket [Agent 3]"),
    ("decide_ticket [Agent 3]", "create_ticket | skip_ticket"),
    ("create_ticket", "send_outbound_reply"),
    ("skip_ticket", "send_outbound_reply"),
    ("send_outbound_reply", "persist_audit_events"),
    ("persist_audit_events", "__end__"),
]


class GraphState(TypedDict):
    runtime: OrchestrationState


class OrchestrationGraph:
    """LangGraph workflow with 3 BFSI agents:

    Agent 1 – IntentClassificationAgent  (classify intent + Neo4j enrichment)
    Agent 2 – QueryResolutionAgent       (KB / Neo4j answer)
    Agent 3 – TicketCreationAgent        (JIRA ticket decision + creation)
    """

    def __init__(
        self,
        repository: CXRepository,
        agent: CXAgent | None = None,
        rag: RAGPipeline | None = None,
        delivery: OutboundDeliveryService | None = None,
        crm: CRMClient | None = None,
        neo4j_client=None,
    ) -> None:
        self.repository = repository
        self.crm = crm or CRMClient()
        self.tickets = TicketManager(repository, self.crm)

        self.neo4j_client = neo4j_client or _try_neo4j()

        # 3 named agents
        self.intent_agent = IntentClassificationAgent(agent, neo4j_client=self.neo4j_client)
        self.resolution_agent = QueryResolutionAgent(rag, neo4j_client=self.neo4j_client)
        self.ticket_agent = TicketCreationAgent(self.tickets)

        # Outbound delivery wrapper (not a named agent, infrastructure concern)
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
            logger.exception("orchestration_failed", extra={**self._common(state), "error": str(exc)})
            try:
                self._audit("workflow_failed", state, details={"error": str(exc)})
            except Exception:
                logger.exception("workflow_failure_audit_failed", extra=self._common(state))
            raise

    # ── Graph construction ────────────────────────────────────────────────

    def _build_workflow(self):
        workflow = StateGraph(GraphState)

        # Infrastructure
        workflow.add_node("receive_message", self._receive_message)
        workflow.add_node("resolve_identity", self._resolve_identity)
        workflow.add_node("load_conversation_context", self._load_context)
        workflow.add_node("detect_ticket_action", self._detect_ticket_action)
        workflow.add_node("resolve_ticket", self._resolve_ticket)

        # Agent 1
        workflow.add_node("classify_intent", self._classify_intent)
        # Agent 2
        workflow.add_node("resolve_query", self._resolve_query)
        # Agent 3 – two sub-nodes: decide + execute
        workflow.add_node("decide_ticket", self._decide_ticket)
        workflow.add_node("create_ticket", self._create_ticket)
        workflow.add_node("skip_ticket", self._skip_ticket)

        # Infrastructure
        workflow.add_node("send_outbound_reply", self._generate_and_send_reply)
        workflow.add_node("persist_audit_events", self._persist_result)

        # Wiring
        workflow.add_edge(START, "receive_message")
        workflow.add_edge("receive_message", "resolve_identity")
        workflow.add_edge("resolve_identity", "load_conversation_context")
        workflow.add_edge("load_conversation_context", "detect_ticket_action")
        workflow.add_conditional_edges(
            "detect_ticket_action",
            self._route_ticket_action,
            {"resolve_ticket": "resolve_ticket", "classify_intent": "classify_intent"},
        )
        workflow.add_edge("resolve_ticket", "send_outbound_reply")
        # Agent chain
        workflow.add_edge("classify_intent", "resolve_query")
        workflow.add_edge("resolve_query", "decide_ticket")
        workflow.add_conditional_edges(
            "decide_ticket",
            self._route_ticket_decision,
            {"ticket_required": "create_ticket", "answer_directly": "skip_ticket"},
        )
        workflow.add_edge("create_ticket", "send_outbound_reply")
        workflow.add_edge("skip_ticket", "send_outbound_reply")
        workflow.add_edge("send_outbound_reply", "persist_audit_events")
        workflow.add_edge("persist_audit_events", END)
        return workflow.compile()

    # ── Infrastructure nodes ──────────────────────────────────────────────

    def _receive_message(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        self._complete(state, WorkflowStep.RECEIVE_MESSAGE, "langgraph", provider=state.message.provider)
        return {"runtime": state}

    def _resolve_identity(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        message = state.message
        is_portal_message = bool(message.metadata.get("portal_graph_customer_id"))
        # Cross-channel linking: look up the sender in Neo4j to find their other identifiers
        # (e.g. a WhatsApp phone maps to an email, or vice versa).  Injecting linked_email /
        # linked_phone into metadata before resolve_customer runs lets the repository merge
        # both channel identities under a single customer record instead of creating two.
        if self.neo4j_client and not is_portal_message:
            try:
                from services.neo4j_service.queries import get_customer_by_identifier
                neo4j_profile = get_customer_by_identifier(self.neo4j_client, message.channel_identifier)
                if neo4j_profile:
                    if neo4j_profile.get("email"):
                        message.metadata["linked_email"] = neo4j_profile["email"]
                        # Use the email as display_name so the frontend can infer a
                        # readable name (e.g. "Fathima Devasahayam") from it.  Only
                        # override generic channel-provided names like "Local WhatsApp
                        # Tester"; a real name already set should be kept as-is.
                        generic = {"local whatsapp tester", "whatsapp user", "unknown", ""}
                        if (not message.display_name or
                                message.display_name.lower() in generic):
                            message.display_name = neo4j_profile["email"]
                    if neo4j_profile.get("phone"):
                        message.metadata["linked_phone"] = neo4j_profile["phone"]
            except Exception:
                logger.exception("neo4j_cross_channel_lookup_failed")
        crm_profile = self.crm.lookup_customer(message.channel.value, message.channel_identifier)
        if crm_profile.status == "synced":
            message.profile_metadata["crm"] = crm_profile.data
            message.metadata["crm_customer_id"] = crm_profile.data.get("customer_id") or crm_profile.data.get("id")
        # Cross-channel linking: if a WhatsApp customer's phone matches a Neo4j BFSI
        # customer that already has an email, inject that email so resolve_customer()
        # will merge the two SQLite identities into one customer_id automatically.
        if self.neo4j_client and message.channel.value == "whatsapp" and not is_portal_message:
            try:
                from services.neo4j_service.queries import get_customer_by_identifier
                neo4j_cust = get_customer_by_identifier(self.neo4j_client, message.channel_identifier)
                if neo4j_cust and neo4j_cust.get("email"):
                    message.profile_metadata.setdefault("linked_email", neo4j_cust["email"])
            except Exception:
                pass

        state.customer = self.repository.resolve_customer(message)
        state.conversation = self.repository.get_or_create_conversation(state.customer_id)
        if neo4j_writer and self.neo4j_client:
            neo4j_writer.upsert_customer(
                self.neo4j_client,
                customer_id=_neo4j_customer_id(state),
                phone=message.channel_identifier if message.channel.value == "whatsapp" else "",
                name=state.customer.get("display_name", ""),
                channel=message.channel.value,
                email=message.metadata.get("linked_email", "") if message.channel.value == "whatsapp" else message.channel_identifier,
            )
        self._audit("inbound_received", state, details={"provider": message.provider})
        if crm_profile.status != "not_configured":
            self._audit("crm_profile_lookup_" + crm_profile.status, state,
                        details={"error": crm_profile.error, **crm_profile.data})
        inbound_turn = self.repository.append_turn(
            conversation_id=state.conversation_id,
            customer_id=state.customer_id,
            channel=message.channel.value,
            direction="inbound",
            text=message.text,
            external_message_id=message.external_message_id,
            subject=message.subject,
            metadata=message.metadata,
        )
        # Phase 1 of 2-phase Neo4j write: create Interaction node immediately ("open")
        # so the graph always has a record even if the AI pipeline fails.
        if neo4j_writer and self.neo4j_client:
            neo4j_writer.write_incoming_interaction(
                self.neo4j_client,
                conversation_id=state.conversation_id,
                customer_id=_neo4j_customer_id(state),
                channel=message.channel.value,
                message_text=message.text,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        self._complete(state, WorkflowStep.RESOLVE_IDENTITY, "identity_resolution",
                       crm_profile_status=crm_profile.status)
        return {"runtime": state}

    def _load_context(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        active_ticket = self.repository.find_active_ticket(state.conversation_id)
        customer_tickets = self.repository.find_open_tickets_for_customer(state.customer_id)

        # Fetch Neo4j graph context once here so BOTH intent and resolution agents share it.
        graph_context: dict = {}
        if self.neo4j_client:
            try:
                from services.neo4j_service.queries import get_customer_context, get_customer_context_by_id
                graph_customer_id = state.message.metadata.get("portal_graph_customer_id")
                graph_context = (
                    get_customer_context_by_id(self.neo4j_client, str(graph_customer_id))
                    if graph_customer_id
                    else get_customer_context(self.neo4j_client, state.message.channel_identifier)
                ) or {}
            except Exception:
                pass

        state.context = {
            "conversation_summary": state.conversation.get("summary", ""),
            "recent_turns": self.repository.list_recent_turns(state.conversation_id),
            "customer_metadata": state.customer.get("metadata", {}),
            "channel": state.message.channel.value,
            "active_ticket": active_ticket.model_dump(mode="json") if active_ticket else None,
            "customer_tickets": customer_tickets,
            "graph_context": graph_context,
        }
        self._complete(state, WorkflowStep.LOAD_CONVERSATION_CONTEXT, "workflow_automation_agent",
                       recent_turn_count=len(state.context["recent_turns"]),
                       active_ticket_id=active_ticket.ticket_id if active_ticket else None,
                       open_ticket_count=len(customer_tickets),
                       graph_customer_id=graph_context.get("customer_id") or None)
        return {"runtime": state}

    def _detect_ticket_action(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        state.ticket_action = self.ticket_agent.detect_action(state.message, state.context)
        self._complete(state, WorkflowStep.DETECT_TICKET_ACTION, self.ticket_agent.name,
                       action=state.ticket_action.action.value, reason=state.ticket_action.reason)
        return {"runtime": state}

    @staticmethod
    def _route_ticket_action(graph_state: GraphState) -> Literal["resolve_ticket", "classify_intent"]:
        return "resolve_ticket" if graph_state["runtime"].ticket_action.action == TicketAction.RESOLVE else "classify_intent"

    def _resolve_ticket(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        active_ticket = state.context["active_ticket"]
        state.ticket = self.ticket_agent.resolve_ticket(active_ticket["ticket_id"])
        state.answer = (
            f"Your support ticket {state.ticket.ticket_id} has been marked as resolved. "
            "Thank you for confirming."
        )
        self._audit("ticket_resolved_by_customer", state, ticket_id=state.ticket.ticket_id,
                    details={"reason": state.ticket_action.reason})
        self._complete(state, WorkflowStep.RESOLVE_TICKET, self.ticket_agent.name,
                       ticket_id=state.ticket.ticket_id, status=state.ticket.status.value)
        return {"runtime": state}

    # ── Agent 1: Intent Classification ───────────────────────────────────

    def _classify_intent(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        state.analysis = self.intent_agent.run(state.message, state.context)
        if state.inbound_turn_id:
            self.repository.update_turn_metadata(state.inbound_turn_id, {"sentiment": state.analysis.sentiment})
            self.repository.update_turn_intent_urgency(
                state.inbound_turn_id,
                state.analysis.intent.value,
                state.analysis.urgency.value,
            )
        self._audit("intent_classified", state, intent=state.analysis.intent.value,
                    details=state.analysis.model_dump())
        self._complete(state, WorkflowStep.CLASSIFY_INTENT, self.intent_agent.name,
                       intent=state.analysis.intent.value, confidence=state.analysis.confidence,
                       urgency=state.analysis.urgency.value, source=state.analysis.analysis_source)
        return {"runtime": state}

    # ── Agent 2: Query / Complaint Resolution ─────────────────────────────

    def _resolve_query(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        intent_str = state.analysis.intent.value if state.analysis else None
        # Pass detected language into context so Groq generator can respond in customer's language
        enriched_context = {
            **state.context,
            "language": state.analysis.language if state.analysis else "en",
            "sentiment": state.analysis.sentiment if state.analysis else "neutral",
        }
        state.resolution = self.resolution_agent.run(state.message, enriched_context, intent=intent_str)
        self._audit("retrieval_performed", state,
                    intent=intent_str or "unknown",
                    details={
                        "confidence": state.resolution.confidence,
                        "citations": state.resolution.citations,
                        "retrieval_backend": state.resolution.retrieval_backend,
                        "retrieval_error": state.resolution.retrieval_error,
                        "resolution_decision": state.resolution.resolution_decision,
                    })
        self._complete(state, WorkflowStep.RETRIEVE_KNOWLEDGE, self.resolution_agent.name,
                       confidence=state.resolution.confidence,
                       citation_count=len(state.resolution.citations),
                       retrieval_backend=state.resolution.retrieval_backend)
        return {"runtime": state}

    # ── Agent 3: Ticket Decision + Creation ───────────────────────────────

    def _decide_ticket(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        state.ticket_decision = self.ticket_agent.decide(state.analysis, state.resolution, state.context)
        self._complete(state, WorkflowStep.DECIDE_RESOLUTION, self.ticket_agent.name,
                       ticket_required=state.ticket_decision.required,
                       reason=state.ticket_decision.reason)
        return {"runtime": state}

    @staticmethod
    def _route_ticket_decision(graph_state: GraphState) -> Literal["ticket_required", "answer_directly"]:
        return "ticket_required" if graph_state["runtime"].ticket_decision.required else "answer_directly"

    def _create_ticket(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        state.ticket = self.ticket_agent.create_or_get(
            state.conversation_id, state.customer_id, state.message,
            state.analysis, state.ticket_decision, state.customer,
        )
        if (
            state.ticket_decision.reason
            and state.ticket_decision.reason.startswith("assisted_resolution_required:")
            and state.resolution
            and state.resolution.answer
        ):
            self.repository.add_ticket_event(
                state.ticket.ticket_id,
                "ai_draft_created",
                "resolution_decision_engine",
                {
                    "draft_response": state.resolution.answer,
                    "resolution_decision": state.resolution.resolution_decision,
                    "requires_human_verification": True,
                },
            )
        self._audit("ticket_created", state, intent=state.analysis.intent.value,
                    ticket_id=state.ticket.ticket_id)
        self._audit("ticket_crm_sync_" + state.ticket.crm_sync_status, state,
                    intent=state.analysis.intent.value, ticket_id=state.ticket.ticket_id,
                    details={
                        "external_ticket_id": state.ticket.external_ticket_id,
                        "external_ticket_url": state.ticket.external_ticket_url,
                        "error": state.ticket.crm_sync_error,
                    })
        self._complete(state, WorkflowStep.CREATE_OR_UPDATE_TICKET, self.ticket_agent.name,
                       ticket_id=state.ticket.ticket_id)
        return {"runtime": state}

    def _skip_ticket(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        self._complete(state, WorkflowStep.CREATE_OR_UPDATE_TICKET, self.ticket_agent.name,
                       skipped=True, reason="ticket_not_required")
        return {"runtime": state}

    # ── Delivery & persistence ────────────────────────────────────────────

    def _generate_and_send_reply(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        if not state.answer:
            state.answer = self.workflow_automation_agent.compose_answer(
                state.resolution,
                state.ticket,
                channel=state.message.channel.value,
                customer_name=state.customer.get("display_name", ""),
            )
        # GAP-I1: Secondary intent processing — if the customer's message contained a second
        # distinct intent that requires manual review (e.g. "check loan AND report fraud"),
        # create a separate ticket for it and append a note so the customer knows both
        # issues are being tracked.  Primary resolution and ticket are unaffected.
        if state.analysis and getattr(state.analysis, "secondary_intent", None):
            try:
                from services.agent_service.orchestration_agents import MANUAL_REVIEW_INTENTS, TicketDecision
                from shared.schemas.intents import Intent
                sec_intent_str = state.analysis.secondary_intent
                try:
                    sec_intent_enum = Intent(sec_intent_str)
                except ValueError:
                    sec_intent_enum = None
                if sec_intent_enum and sec_intent_enum in MANUAL_REVIEW_INTENTS:
                    sec_analysis = state.analysis.model_copy(update={
                        "intent": sec_intent_enum,
                        "secondary_intent": None,
                    })
                    sec_decision = TicketDecision(
                        required=True,
                        reason=f"secondary_intent_manual_review:{sec_intent_str}",
                    )
                    sec_ticket = self.ticket_agent.create_or_get(
                        state.conversation_id, state.customer_id, state.message,
                        sec_analysis, sec_decision, state.customer,
                    )
                    team = sec_ticket.assigned_team.replace("_", " ")
                    ref = (
                        f"*{sec_ticket.ticket_id}*"
                        if state.message.channel.value == "whatsapp"
                        else sec_ticket.ticket_id
                    )
                    sec_note = (
                        f"\n\nWe have also flagged your {sec_intent_str.replace('_', ' ')} "
                        f"for our {team} team (reference: {ref})."
                    )
                    state.answer = (state.answer or "") + sec_note
            except Exception:
                pass
        self._audit("answer_generated", state, intent=self._intent(state),
                    ticket_id=state.ticket.ticket_id if state.ticket else None)
        state.delivery = self.workflow_automation_agent.send_reply(state.message, state.answer)
        self._audit(
            "outbound_sent" if state.delivery["status"] == "sent" else "outbound_failed",
            state, intent=self._intent(state),
            ticket_id=state.ticket.ticket_id if state.ticket else None,
            details=state.delivery,
        )
        self._complete(state, WorkflowStep.SEND_OUTBOUND_REPLY, self.workflow_automation_agent.name,
                       delivery_status=state.delivery["status"])
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
                "resolution_decision": state.resolution.resolution_decision if state.resolution else {},
                "provider_message_id": provider_message_id,
                "provider_response": state.delivery.get("provider_response"),
            },
        )
        if state.resolution:
            self.repository.add_retrieval_evidence(outbound_turn["turn_id"], state.resolution.contexts)
        self.repository.update_conversation_summary(state.conversation_id, self._summary(state.conversation_id))
        if neo4j_writer and self.neo4j_client and state.analysis:
            # Phase 2 of 2-phase write: close the Interaction node and create ResolutionMemory.
            neo4j_writer.update_interaction_resolution(
                self.neo4j_client,
                conversation_id=state.conversation_id,
                customer_id=_neo4j_customer_id(state),
                resolution=state.answer or "",
                intent=state.analysis.intent.value,
                sentiment=state.analysis.sentiment,
                product_id=_extract_product_ref(state),
                embedding_str=_extract_embedding(state.resolution),
                urgency=state.analysis.urgency.value,
            )
            if state.ticket:
                neo4j_writer.upsert_ticket_node(
                    self.neo4j_client,
                    ticket_id=state.ticket.ticket_id,
                    customer_id=_neo4j_customer_id(state),
                    intent=state.analysis.intent.value,
                    priority=state.ticket.priority.value if hasattr(state.ticket.priority, "value") else str(state.ticket.priority),
                    status=state.ticket.status.value if hasattr(state.ticket.status, "value") else str(state.ticket.status),
                )
        self._complete(state, WorkflowStep.PERSIST_AUDIT_EVENTS, "workflow_automation_agent",
                       outbound_turn_id=outbound_turn["turn_id"])
        self._audit("workflow_completed", state, intent=self._intent(state),
                    ticket_id=state.ticket.ticket_id if state.ticket else None,
                    details={"steps": [entry.step.value for entry in state.workflow_trace]})
        return {"runtime": state}

    # ── Helpers ───────────────────────────────────────────────────────────

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
        self._audit("workflow_step_completed", state, details={"step": step.value, "agent": agent, **details})

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
        return state.analysis.intent.value if state.analysis else "unknown"

    @staticmethod
    def _resolved(state: OrchestrationState) -> bool:
        # Only mark the conversation resolved when the customer explicitly confirms it.
        # Answering a query without creating a ticket is NOT resolution — the customer
        # may send follow-up messages and must stay in the same conversation thread.
        return state.ticket_action.action == TicketAction.RESOLVE

    def _audit(self, event_type: str, state: OrchestrationState, **values) -> None:
        self.repository.add_audit_event(event_type, **self._common(state), **values)


def _try_neo4j():
    """Return a Neo4jClient if NEO4J_ENABLED=true and package is installed, else None."""
    try:
        import os
        if os.getenv("NEO4J_ENABLED", "true").lower() != "true":
            return None
        from services.neo4j_service.client import Neo4jClient
        return Neo4jClient()
    except Exception:
        return None


def _neo4j_customer_id(state: "OrchestrationState") -> str:  # type: ignore[name-defined]
    """Use portal graph CustomerID for Neo4j writes when the message came from the portal."""
    if state.message and state.message.metadata.get("portal_graph_customer_id"):
        return str(state.message.metadata["portal_graph_customer_id"])
    return state.customer_id or ""


def _extract_product_ref(state: "OrchestrationState") -> str:  # type: ignore[name-defined]
    """Derive the product_id key for ResolutionMemory from the conversation context."""
    graph_ctx = state.context.get("graph_context", {}) if state.context else {}
    intent = state.analysis.intent.value if state.analysis else ""
    if "loan" in intent:
        loans = graph_ctx.get("loans", [])
        return loans[0].get("loan_id", "loan_general") if loans else "loan_general"
    if any(k in intent for k in ("claim", "insurance", "policy")):
        claims = graph_ctx.get("claims", [])
        return claims[0].get("claim_id", "insurance_general") if claims else "insurance_general"
    return "general"


def _extract_embedding(resolution) -> str:
    """Extract the first context embedding vector as a compact string for Neo4j storage.

    Returns empty string when no vector is available (e.g., Neo4j-sourced answers).
    """
    if resolution is None:
        return ""
    contexts = getattr(resolution, "contexts", []) or []
    for ctx in contexts:
        emb = ctx.get("embedding")
        if emb:
            # Store as comma-joined string; Neo4j will store as a string property
            # (vector index applies when the value is a list — upgrade path for later)
            if isinstance(emb, (list, tuple)):
                return ",".join(str(round(float(v), 6)) for v in emb[:384])
            return str(emb)[:2000]
    return ""
