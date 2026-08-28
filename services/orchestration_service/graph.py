import logging
import time
from datetime import datetime, timezone
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from services.agent_service.cx_agent import CXAgent
from services.agent_service.orchestration_agents import (
    CustomerValidationAgent,
    IntentClassificationAgent,
    QueryResolutionAgent,
    TicketAction,
    TicketCreationAgent,
    TicketSelection,
    WorkflowAutomationAgent,
)
from services.channel_service.delivery import OutboundDeliveryService
from services.crm_service.client import CRMClient
from services.orchestration_service.state import OrchestrationState, WorkflowStep
from services.observability_service import langfuse_workflow_trace, llm_observation_context
from services.persistence_service.repository import CXRepository
from services.rag_service.rag_pipeline import RAGPipeline
from services.ticket_service.ticket_manager import TicketManager
from services.workflow_service.review_gate import should_hold_for_review
from shared.schemas.messages import InboundMessage
from shared.schemas.responses import ChannelResponse

try:
    from services.neo4j_service import writer as neo4j_writer
except Exception:
    neo4j_writer = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

ORCHESTRATION_ENGINE = "langgraph_state_graph"

# Human-in-the-loop: customer-facing message sent when the review gate HOLDS the AI reply
# for a human agent to review. The AI's real answer is kept as an editable reply_draft.
HOLDING_MESSAGE = "Support Agent will help you with this shortly ..."

# Human-readable edge map shown in /admin/orchestration/definition
WORKFLOW_EDGES = [
    ("__start__", "receive_message"),
    ("receive_message", "resolve_identity"),
    ("resolve_identity", "load_conversation_context"),
    ("load_conversation_context", "check_has_open_case"),
    ("check_has_open_case", "detect_ticket_action | classify_intent [Agent 1]"),
    ("detect_ticket_action", "select_ticket_to_resolve | classify_intent [Agent 1]"),
    ("select_ticket_to_resolve", "resolve_ticket | send_outbound_reply (ask which ticket)"),
    ("resolve_ticket", "send_outbound_reply"),
    ("classify_intent [Agent 1]", "validate_customer"),
    ("validate_customer", "resolve_query [Agent 2] | reject_unregistered_customer"),
    ("reject_unregistered_customer", "send_outbound_reply"),
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
    """LangGraph workflow with 4 BFSI agents:

    Agent 1 – IntentClassificationAgent  (classify intent + Neo4j enrichment)
    Agent 1b – CustomerValidationAgent   (confirm registered customer for account-specific intents)
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
        resolution_engine=None,
    ) -> None:
        self.repository = repository
        self.crm = crm or CRMClient()
        self.neo4j_client = neo4j_client or _try_neo4j()

        # The graph client MUST reach the manager: update_status mirrors a resolved
        # ticket onto its Ticket node, and get_open_cases reads the GRAPH, not SQLite.
        # Without it a customer-resolved ticket stayed 'open' in Neo4j while SQLite said
        # 'resolved', so the model kept being fed a closed case as trusted context. The
        # admin route (routes/tickets.py) always passed it; this path did not, so the
        # same action behaved differently depending on who performed it.
        self.tickets = TicketManager(repository, self.crm, neo4j_client=self.neo4j_client)

        # Named agents
        self.intent_agent = IntentClassificationAgent(agent, neo4j_client=self.neo4j_client)
        self.validation_agent = CustomerValidationAgent(neo4j_client=self.neo4j_client)
        self.resolution_agent = QueryResolutionAgent(rag, neo4j_client=self.neo4j_client, resolution_engine=resolution_engine)
        self.ticket_agent = TicketCreationAgent(self.tickets)
        # Share the ticket agent's LLM with the manager's tier-4 ticket referee
        # (one generator instance; TicketManager stays LLM-free by default).
        self.tickets.generator = self.ticket_agent.generator

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
            with langfuse_workflow_trace(
                name="omnichannel_message",
                input_text=message.text,
                tags=[message.channel.value],
                metadata={
                    "correlation_id": state.message.correlation_id,
                    "message_id": state.message_id,
                    "channel": message.channel.value,
                    "provider": message.provider,
                },
            ) as trace:
                result = self.workflow.invoke({"runtime": state})
                state = result["runtime"]
                response = self._response(state)
                if trace:
                    trace.update(
                        output=response.message if _capture_langfuse_io() else None,
                        metadata={
                            "correlation_id": response.correlation_id,
                            "conversation_id": response.conversation_id,
                            "customer_id": response.customer_id,
                            "channel": message.channel.value,
                            "intent": response.intent,
                            "sentiment": response.sentiment,
                            "urgency": response.urgency,
                            "ticket_id": response.ticket_id,
                            "retrieval_backend": response.retrieval_backend,
                            "llm_used": response.llm_used,
                            "workflow_steps": [entry["step"] for entry in response.workflow_trace],
                        },
                    )
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
        workflow.add_node("check_has_open_case", self._check_has_open_case)
        workflow.add_node("detect_ticket_action", self._detect_ticket_action)
        workflow.add_node("select_ticket_to_resolve", self._select_ticket_to_resolve)
        workflow.add_node("resolve_ticket", self._resolve_ticket)

        # Agent 1
        workflow.add_node("classify_intent", self._classify_intent)
        # Agent 1b
        workflow.add_node("validate_customer", self._validate_customer)
        workflow.add_node("reject_unregistered_customer", self._reject_unregistered_customer)
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
        workflow.add_edge("load_conversation_context", "check_has_open_case")
        # The customer's case state decides the branch BEFORE anything inspects the
        # message: no open case and there is nothing to close or ask about, so the turn
        # goes straight to the Agent 1 chain.
        workflow.add_conditional_edges(
            "check_has_open_case",
            self._route_has_open_case,
            {"detect_ticket_action": "detect_ticket_action", "classify_intent": "classify_intent"},
        )
        workflow.add_conditional_edges(
            "detect_ticket_action",
            self._route_ticket_action,
            {"select_ticket_to_resolve": "select_ticket_to_resolve", "classify_intent": "classify_intent"},
        )
        workflow.add_conditional_edges(
            "select_ticket_to_resolve",
            self._route_ticket_selection,
            {"resolve_ticket": "resolve_ticket", "ask_which_ticket": "send_outbound_reply"},
        )
        workflow.add_edge("resolve_ticket", "send_outbound_reply")
        # Agent chain
        workflow.add_edge("classify_intent", "validate_customer")
        workflow.add_conditional_edges(
            "validate_customer",
            self._route_customer_validation,
            {"proceed": "resolve_query", "unregistered": "reject_unregistered_customer"},
        )
        workflow.add_edge("reject_unregistered_customer", "send_outbound_reply")
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
                    # Use the customer's REAL name from Neo4j as display_name (drives both
                    # the admin inbox and the reply greeting).  Neo4j is the verified BFSI
                    # master record, so its name is AUTHORITATIVE and always wins over the
                    # channel-provided profile string — which is self-set and often junk
                    # (".", "whatsapp user", or an email that would mangle the greeting into
                    # "Sayantini S 55").  A prior narrower version only overrode a fixed
                    # allow-list of generic names and left junk like "." untouched.
                    if neo4j_profile.get("name"):
                        message.display_name = neo4j_profile["name"]
                    if neo4j_profile.get("phone"):
                        message.metadata["linked_phone"] = neo4j_profile["phone"]
            except Exception:
                logger.exception("neo4j_cross_channel_lookup_failed")

        # Portal/web-chat messages carry portal_graph_customer_id but skip the block above.
        # Pull the matched customer's real name from Neo4j so the SQLite display_name (and
        # therefore the admin inbox) shows "Sayantini Sarkar" instead of the raw portal
        # username ("sayantini_v2"). Only override a username-style/generic display_name.
        if self.neo4j_client and is_portal_message:
            try:
                from services.neo4j_service.queries import get_customer_by_id
                graph_id = message.metadata.get("portal_graph_customer_id")
                neo4j_profile = get_customer_by_id(self.neo4j_client, str(graph_id)) if graph_id else None
                if neo4j_profile and neo4j_profile.get("name"):
                    portal_user = str(message.metadata.get("portal_user_id", "")).lower()
                    current = (message.display_name or "").lower()
                    if not current or current == portal_user:
                        message.display_name = neo4j_profile["name"]
            except Exception:
                logger.exception("neo4j_portal_name_lookup_failed")
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
        # Skip ALL Neo4j customer/interaction writes when the resolved graph id is NOT a real
        # seeded BFSI customer. Writing a bare node would make an unknown sender look
        # "registered" (with no data) and bypass the reject-unregistered flow. This must apply
        # on EVERY channel: an unverified email/WhatsApp sender resolves to a synthetic cust_…
        # id that does not exist in the graph, so the guard skips the write; a known customer
        # resolves to their real CRN… id, is found, and the write proceeds unchanged.
        # (Previously this check ran for portal messages only, which let email/WhatsApp create
        # phantom cust_… nodes for unverified senders.) Cached per-request.
        graph_customer_id = _neo4j_customer_id(state, self.neo4j_client)
        neo4j_customer_exists = True
        if self.neo4j_client:
            try:
                from services.neo4j_service.queries import get_customer_by_id
                neo4j_customer_exists = bool(get_customer_by_id(self.neo4j_client, graph_customer_id))
            except Exception:
                neo4j_customer_exists = False
        write_neo4j = bool(neo4j_writer and self.neo4j_client and neo4j_customer_exists)
        if write_neo4j:
            # Only write a real email. For email-channel messages the channel_identifier
            # IS the email; for whatsapp/web_chat it is a phone/session id, so fall back to
            # linked_email (or portal contact) and never write the raw identifier — otherwise
            # a value like "web_session:<user>" would overwrite the real customer's email.
            linked_email = message.metadata.get("linked_email", "")
            portal_contact = message.metadata.get("portal_contact_identifier", "")
            if message.channel.value == "email":
                neo4j_email = message.channel_identifier
            elif "@" in str(linked_email):
                neo4j_email = linked_email
            elif "@" in str(portal_contact):
                neo4j_email = portal_contact
            else:
                neo4j_email = ""
            neo4j_writer.upsert_customer(
                self.neo4j_client,
                customer_id=graph_customer_id,
                phone=message.channel_identifier if message.channel.value == "whatsapp" else "",
                name=state.customer.get("display_name", ""),
                channel=message.channel.value,
                email=neo4j_email,
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
        # Remember the inbound turn so later steps can reference it (sentiment metadata, and
        # the held-draft's inbound_turn_id used to thread the manual email reply — see
        # apps/api/routes/reply_drafts.py). Previously unset, leaving inbound_turn_id None.
        state.inbound_turn_id = inbound_turn["turn_id"]
        # Phase 1 of 2-phase Neo4j write: create Interaction node immediately ("open")
        # so the graph always has a record even if the AI pipeline fails. Skipped for
        # unregistered portal users (write_neo4j is False) — no customer node to link to.
        if write_neo4j:
            neo4j_writer.write_incoming_interaction(
                self.neo4j_client,
                conversation_id=state.conversation_id,
                customer_id=graph_customer_id,
                channel=message.channel.value,
                message_text=message.text,
                timestamp=datetime.now(timezone.utc).isoformat(),
                # One node per MESSAGE. Without this the node is keyed on the
                # conversation and each turn overwrites the last, so the graph keeps
                # only the customer's most recent sentence and can never show the
                # history of a case.
                turn_id=state.inbound_turn_id,
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

    # ── open-case gate + ticket-side selection ─────────────────────────────

    def _check_has_open_case(self, graph_state: GraphState) -> dict:
        """Binary node: 1 when this customer has at least one OPEN ticket, else 0.

        The question is about the CUSTOMER's state, not about this message — someone with
        three open cases asking a brand-new question is still 1. That state decides which
        half of the graph the turn belongs in, and it is settled once, here, immediately
        after load_conversation_context has fetched the tickets.

        Establishing it as a node rather than an inline lambda matters for two reasons.
        It is visible: the 0/1 shows up in the workflow trace, so the branch a turn took
        can be read off the record instead of inferred. And it is single-sourced: every
        step below reads this one answer rather than re-deriving its own, which is exactly
        how a customer with no tickets used to slip past a local `if tickets:` into RAG and
        be handed an escalation ticket they never asked for.

        Counted from customer_tickets — all open tickets on ANY channel, not just this
        conversation's active one — because a customer who opened a case on WhatsApp and
        wrote in by email has an open case either way.
        """
        state = graph_state["runtime"]
        open_tickets = state.context.get("customer_tickets") or []
        state.has_open_case = 1 if open_tickets else 0
        self._complete(state, WorkflowStep.CHECK_HAS_OPEN_CASE, "workflow_automation_agent",
                       has_open_case=state.has_open_case, open_ticket_count=len(open_tickets))
        return {"runtime": state}

    @staticmethod
    def _route_has_open_case(graph_state: GraphState) -> Literal["detect_ticket_action", "classify_intent"]:
        """No open case → nothing to close and nothing to ask about; answer the question."""
        return "detect_ticket_action" if graph_state["runtime"].has_open_case == 1 else "classify_intent"

    @staticmethod
    def _route_ticket_action(graph_state: GraphState) -> Literal["select_ticket_to_resolve", "classify_intent"]:
        """Within the ticket branch: is this turn asking to CLOSE a case, or something else?"""
        return (
            "select_ticket_to_resolve"
            if graph_state["runtime"].ticket_action.action == TicketAction.RESOLVE
            else "classify_intent"
        )

    def _select_ticket_to_resolve(self, graph_state: GraphState) -> dict:
        """Disambiguation only — decide WHICH ticket, kept separate from resolve_ticket
        (which just performs the resolution) so the two concerns don't blur together."""
        state = graph_state["runtime"]
        selection: TicketSelection = self.ticket_agent.select_ticket(state.message, state.context)
        state.target_ticket_id = selection.target_ticket_id
        state.ticket_clarification_needed = selection.needs_clarification
        state.matching_open_tickets = selection.candidates
        if selection.needs_clarification:
            options = ", ".join(
                f"{t['ticket_id']} ({(t.get('title') or t.get('intent') or 'request')})"
                for t in selection.candidates
            )
            state.answer = (
                "You have more than one open ticket for this kind of request: "
                f"{options}. Could you tell me which ticket ID you'd like to resolve?"
            )
            self._audit("ticket_resolution_clarification_requested", state,
                        details={"candidates": [t["ticket_id"] for t in selection.candidates]})
        self._complete(state, WorkflowStep.SELECT_TICKET_TO_RESOLVE, self.ticket_agent.name,
                       target_ticket_id=state.target_ticket_id,
                       needs_clarification=state.ticket_clarification_needed,
                       reason=selection.reason)
        return {"runtime": state}

    @staticmethod
    def _route_ticket_selection(graph_state: GraphState) -> Literal["resolve_ticket", "ask_which_ticket"]:
        return "ask_which_ticket" if graph_state["runtime"].ticket_clarification_needed else "resolve_ticket"

    def _resolve_ticket(self, graph_state: GraphState) -> dict:
        """Pure resolution: mark the already-selected target ticket resolved."""
        state = graph_state["runtime"]
        state.ticket = self.ticket_agent.resolve_ticket(state.target_ticket_id)
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
        with llm_observation_context(**self._llm_context(state, "intent_classification_agent")):
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

    # ── Agent 1b: Customer Validation ─────────────────────────────────────

    def _validate_customer(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        intent = state.analysis.intent if state.analysis else None
        state.customer_validation = self.validation_agent.validate(intent, state.context)
        self._complete(state, WorkflowStep.VALIDATE_CUSTOMER, self.validation_agent.name,
                       validation_required=state.customer_validation.validation_required,
                       is_registered=state.customer_validation.is_registered,
                       reason=state.customer_validation.reason)
        return {"runtime": state}

    @staticmethod
    def _route_customer_validation(graph_state: GraphState) -> Literal["proceed", "unregistered"]:
        validation = graph_state["runtime"].customer_validation
        if validation.validation_required and not validation.is_registered:
            return "unregistered"
        return "proceed"

    def _reject_unregistered_customer(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        if state.message.channel.value == "email":
            state.answer = (
                "Dear Customer,\n\n"
                "We were unable to verify your account using the email address you contacted us from. "
                "For your security, please write to us again using the email address or mobile number "
                "registered with your account so we can look into this for you.\n\n"
                "Warm regards,\nCustomer Support Team"
            )
        else:
            state.answer = (
                "We couldn't verify your account with this contact number. Please reach out to us "
                "using the mobile number or email address registered with your account so we can help."
            )
        self._audit("customer_validation_failed", state, intent=self._intent(state),
                    details={"reason": state.customer_validation.reason})
        self._complete(state, WorkflowStep.REJECT_UNREGISTERED_CUSTOMER, self.validation_agent.name,
                       reason=state.customer_validation.reason)
        return {"runtime": state}

    # ── Agent 2: Query / Complaint Resolution ─────────────────────────────

    def _resolve_query(self, graph_state: GraphState) -> dict:
        state = graph_state["runtime"]
        intent_str = state.analysis.intent.value if state.analysis else None
        # Pass detected language into context so Groq generator can respond in customer's language
        enriched_context = {
            **state.context,
            "language": state.analysis.language if state.analysis else "en",
        }
        with llm_observation_context(**self._llm_context(state, "query_resolution_agent", intent=intent_str)):
            state.resolution = self.resolution_agent.run(state.message, enriched_context, intent=intent_str)
        self._audit("retrieval_performed", state,
                    intent=intent_str or "unknown",
                    details={
                        "confidence": state.resolution.confidence,
                        "citations": state.resolution.citations,
                        "retrieval_backend": state.resolution.retrieval_backend,
                        "retrieval_error": state.resolution.retrieval_error,
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
            graph_context=state.context.get("graph_context", {}) if state.context else {},
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
        customer_rejected = state.customer_validation.validation_required and not state.customer_validation.is_registered
        if state.analysis and getattr(state.analysis, "secondary_intent", None) and not customer_rejected:
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
                        graph_context=state.context.get("graph_context", {}) if state.context else {},
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

        # ── Human-in-the-loop review gate ──────────────────────────────────────
        # If a ticket is required (escalation / L2 / L3 / L1-via-rule), HOLD the AI answer as
        # an editable draft for a human agent instead of auto-delivering it. The customer
        # receives a holding message now; the agent edits + sends the real answer manually
        # (see services/workflow_service/review_gate.py and apps/api/routes/reply_drafts.py).
        gate = should_hold_for_review(state.ticket_decision, state.resolution)
        if gate.hold and state.answer:
            try:
                draft = self.repository.add_reply_draft(
                    conversation_id=state.conversation_id,
                    customer_id=state.customer_id,
                    channel=state.message.channel.value,
                    draft_text=state.answer,
                    ticket_id=state.ticket.ticket_id if state.ticket else None,
                    inbound_turn_id=state.inbound_turn_id,
                    hold_reason=gate.reason,
                    reason_code=gate.reason_code,
                    channel_identifier=state.message.channel_identifier,
                    provider=state.message.provider,
                    # Confidence scores live at hold time — surface them to the reviewing admin.
                    retrieval_confidence=(state.resolution.confidence if state.resolution else None),
                    intent_confidence=(state.analysis.confidence if state.analysis else None),
                )
                state.held_for_review = True
                state.draft_id = draft["draft_id"]
                # Replace the outbound text with the holding message: this is what actually
                # gets delivered to the customer AND persisted as the outbound turn.
                state.answer = HOLDING_MESSAGE
                self._audit("reply_held_for_review", state, intent=self._intent(state),
                            ticket_id=state.ticket.ticket_id if state.ticket else None,
                            details={"draft_id": draft["draft_id"], "hold_reason": gate.reason,
                                     "reason_code": gate.reason_code})
            except Exception:
                # If draft persistence fails, fall back to the original auto-send behavior
                # rather than dropping the customer's reply entirely.
                logger.exception("reply_draft_hold_failed", extra={"conversation_id": state.conversation_id})
                state.held_for_review = False

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
                "provider_message_id": provider_message_id,
                "provider_response": state.delivery.get("provider_response"),
            },
        )
        if state.resolution:
            self.repository.add_retrieval_evidence(outbound_turn["turn_id"], state.resolution.contexts)
        self.repository.update_conversation_summary(state.conversation_id, self._summary(state.conversation_id))
        # Skip Phase-2 Neo4j writes for unregistered senders (no real customer node) on ANY
        # channel, so we don't leave orphan Interaction/Ticket nodes for senders we rejected.
        # An unverified email/WhatsApp/portal sender resolves to a synthetic cust_… id that is
        # not in the graph → skipped; a known customer resolves to their real CRN… id → written.
        neo4j_customer_exists = True
        if self.neo4j_client:
            try:
                from services.neo4j_service.queries import get_customer_by_id
                neo4j_customer_exists = bool(
                    get_customer_by_id(self.neo4j_client, _neo4j_customer_id(state, self.neo4j_client))
                )
            except Exception:
                neo4j_customer_exists = False
        if neo4j_writer and self.neo4j_client and state.analysis and neo4j_customer_exists:
            # Phase 2 of 2-phase write: close the Interaction node and create ResolutionMemory.
            neo4j_writer.update_interaction_resolution(
                self.neo4j_client,
                conversation_id=state.conversation_id,
                customer_id=_neo4j_customer_id(state, self.neo4j_client),
                # The RESOLUTION BODY, not the delivered reply. state.answer has already
                # been through compose_answer, which prepends "Hi <customer name>," and,
                # on email, a sign-off — so storing it would put one customer's name into
                # an answer meant to be reused for the next customer with the same problem.
                # This is exactly the particulars-leak the memory cache was disabled over.
                resolution=(state.resolution.answer if state.resolution else state.answer) or "",
                intent=state.analysis.intent.value,
                sentiment=state.analysis.sentiment,
                product_id=_extract_product_ref(state),
                embedding_str=_extract_embedding(state.resolution),
                urgency=state.analysis.urgency.value,
                # Same key write_incoming_interaction used, or this MERGEs a second node
                # and the per-message one never leaves 'open'.
                turn_id=state.inbound_turn_id,
                # Cross-customer learning key: the KIND of problem, not this customer's
                # account. ticket_scope is already "intent:subtype" (e.g.
                # "transaction_dispute:imps"), the same distinction select_ticket uses to
                # tell a card dispute from a UPI one. Falls back to the bare intent when a
                # turn produced no ticket.
                memory_key=_memory_key(state),
            )
            if state.ticket:
                neo4j_writer.upsert_ticket_node(
                    self.neo4j_client,
                    ticket_id=state.ticket.ticket_id,
                    customer_id=_neo4j_customer_id(state, self.neo4j_client),
                    intent=state.analysis.intent.value,
                    priority=state.ticket.priority.value if hasattr(state.ticket.priority, "value") else str(state.ticket.priority),
                    status=state.ticket.status.value if hasattr(state.ticket.status, "value") else str(state.ticket.status),
                    ticket_scope=(state.ticket.metadata or {}).get("ticket_scope"),
                    title=state.ticket.title,
                )
                # Attach this message to its ticket, so the graph can answer "what has
                # been said about this case?" and not only "what does this customer
                # hold?". Runs after upsert_ticket_node so both nodes exist.
                if state.inbound_turn_id:
                    neo4j_writer.link_interaction_to_ticket(
                        self.neo4j_client,
                        turn_id=state.inbound_turn_id,
                        ticket_id=state.ticket.ticket_id,
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
            workflow_status=(
                "ticket_resolution_clarification_needed" if state.ticket_clarification_needed else
                "ticket_closed" if state.ticket_action.action == TicketAction.RESOLVE else
                "customer_validation_required" if (
                    state.customer_validation.validation_required and not state.customer_validation.is_registered
                ) else
                ("human_follow_up" if state.ticket else "answer_delivered")
            ),
            analysis_source=state.analysis.analysis_source if state.analysis else "operational_command",
            rag_contexts=state.resolution.contexts if state.resolution else [],
            citations=state.resolution.citations if state.resolution else [],
            retrieval_backend=state.resolution.retrieval_backend if state.resolution else "not_required",
            llm_model=state.resolution.llm.get("model") if state.resolution else None,
            llm_used=state.resolution.llm.get("llm_used", False) if state.resolution else False,
            outbound_status=state.delivery["status"],
            outbound_error=state.delivery.get("error"),
            held_for_review=state.held_for_review,
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

    def _llm_context(self, state: OrchestrationState, agent: str, intent: str | None = None) -> dict:
        return {
            **self._common(state),
            "agent": agent,
            "intent": intent or (state.analysis.intent.value if state.analysis else None),
            "ticket_id": state.ticket.ticket_id if state.ticket else None,
            "resolution_level": (
                state.resolution.resolution_decision.get("resolution_level")
                if state.resolution and state.resolution.resolution_decision
                else None
            ),
            "retrieval_backend": state.resolution.retrieval_backend if state.resolution else None,
        }

    @staticmethod
    def _intent(state: OrchestrationState) -> str:
        if state.ticket_action.action == TicketAction.RESOLVE:
            return "ticket_resolution"
        if state.customer_validation.validation_required and not state.customer_validation.is_registered:
            return "customer_not_registered"
        return state.analysis.intent.value if state.analysis else "unknown"

    @staticmethod
    def _resolved(state: OrchestrationState) -> bool:
        # Only mark the conversation resolved when the customer explicitly confirms it AND
        # a specific ticket was actually resolved. When they have multiple open tickets of
        # the same kind, we've only asked which one — nothing is resolved yet.
        return state.ticket_action.action == TicketAction.RESOLVE and not state.ticket_clarification_needed

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


def _neo4j_customer_id(state: "OrchestrationState", client=None) -> str:  # type: ignore[name-defined]
    """Resolve the id to use for Neo4j writes, in the graph's own ``CRN…`` namespace.

    Portal messages already carry the resolved graph id. For whatsapp/email the state's
    ``customer_id`` is the SQLite ``cust_…`` hash, which is a DIFFERENT namespace from the
    graph's ``CRN…`` ids — writing it means ``MATCH (c:Customer {customer_id: 'cust_…'})``
    matches nothing, so ticket/interaction writes silently produced no nodes. Resolve the
    sender's phone/email against the graph (same lookup the agent panel uses) to get the
    real ``CRN…``.

    Falls back to the ``cust_…`` id when no graph customer matches — an unverified sender,
    which the callers' existence check then correctly skips (no phantom nodes).
    """
    if state.message and state.message.metadata.get("portal_graph_customer_id"):
        return str(state.message.metadata["portal_graph_customer_id"])

    fallback = state.customer_id or ""
    if client is None:
        return fallback

    # Cached per message — this helper is called on several write paths per turn.
    cached = state.context.get("_neo4j_graph_customer_id") if state.context is not None else None
    if cached is not None:
        return str(cached)

    resolved = fallback
    try:
        from services.neo4j_service.queries import get_customer_by_identifier
        for identifier in _graph_identifiers(state):
            found = get_customer_by_identifier(client, identifier)
            if found and found.get("customer_id"):
                resolved = str(found["customer_id"])
                break
    except Exception:
        logger.warning("neo4j_customer_id_resolve_failed", exc_info=True)
        resolved = fallback

    if state.context is not None:
        state.context["_neo4j_graph_customer_id"] = resolved
    return resolved


def _graph_identifiers(state: "OrchestrationState") -> list[str]:  # type: ignore[name-defined]
    """Candidate phone/email identifiers for resolving the sender to a graph Customer."""
    meta = state.message.metadata if state.message else {}
    candidates = [
        meta.get("linked_email"),
        meta.get("portal_contact_identifier"),
        state.message.channel_identifier if state.message else None,
        (state.customer or {}).get("metadata_json", {}).get("email")
        if isinstance((state.customer or {}).get("metadata_json"), dict) else None,
    ]
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        c = str(c).strip() if c else ""
        # web_session:<user> is a portal session handle, never a graph identifier.
        if not c or c.startswith("web_session:") or c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def _memory_key(state) -> str:
    """The ResolutionMemory key: the kind of problem, shared across customers.

    Prefers the ticket's ticket_scope ("transaction_dispute:imps"), which already
    encodes intent + subtype. Without a ticket, falls back to "<intent>:general" so
    unticketed turns still group by intent rather than colliding into one bucket.
    """
    scope = None
    if getattr(state, "ticket", None) is not None:
        scope = (state.ticket.metadata or {}).get("ticket_scope")
    if scope:
        return str(scope)
    intent = state.analysis.intent.value if state.analysis else "unknown"
    return f"{intent}:general"


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


def _capture_langfuse_io() -> bool:
    import os

    return os.getenv("LANGFUSE_CAPTURE_IO", "false").lower() == "true"
