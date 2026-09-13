from enum import StrEnum

from pydantic import BaseModel, Field

from services.agent_service.orchestration_agents import (
    CustomerValidationResult,
    QueryResolution,
    TicketActionDecision,
    TicketDecision,
)
from shared.schemas.intents import IntentResult
from shared.schemas.messages import InboundMessage
from shared.schemas.tickets import Ticket


class WorkflowStep(StrEnum):
    RECEIVE_MESSAGE = "receive_message"
    RESOLVE_IDENTITY = "resolve_identity"
    LOAD_CONVERSATION_CONTEXT = "load_conversation_context"
    CHECK_HAS_OPEN_CASE = "check_has_open_case"
    DETECT_TICKET_ACTION = "detect_ticket_action"
    SELECT_TICKET_TO_CLOSE = "select_ticket_to_close"
    # The customer's words PROPOSE a close; they no longer perform one. A "thank you" is
    # politeness, not a resolution decision - and on the live fraud case it fired YES while
    # the CRM sync had failed and approval was still pending, closing a regulated matter
    # nobody had looked at. This step records the proposal; a human decides.
    PROPOSE_CLOSE = "propose_close"
    CLASSIFY_INTENT = "classify_intent"
    VALIDATE_CUSTOMER = "validate_customer"
    REJECT_UNREGISTERED_CUSTOMER = "reject_unregistered_customer"
    RETRIEVE_KNOWLEDGE = "retrieve_knowledge"
    DECIDE_RESOLUTION = "decide_resolution"
    CREATE_OR_UPDATE_TICKET = "create_or_update_ticket"
    CLOSE_TICKET = "close_ticket"
    SEND_OUTBOUND_REPLY = "send_outbound_reply"
    PERSIST_AUDIT_EVENTS = "persist_audit_events"


class WorkflowTraceEntry(BaseModel):
    step: WorkflowStep
    agent: str
    status: str = "completed"
    details: dict = Field(default_factory=dict)


class OrchestrationState(BaseModel):
    message: InboundMessage
    message_id: str
    customer: dict | None = None
    conversation: dict | None = None
    context: dict = Field(default_factory=dict)
    ticket_action: TicketActionDecision = Field(default_factory=TicketActionDecision)
    # Binary flag set by the check_has_open_case node: 1 when this customer has at least
    # one OPEN ticket, 0 when they have none. It answers "what state is this customer in",
    # not "what is this message" — a customer with three open cases asking a fresh question
    # is still 1. Established once, immediately after the tickets are loaded, so every step
    # below reads one answer instead of each re-deriving its own (which is how a zero-ticket
    # customer used to fall past `if tickets:` into RAG and be handed a ticket they never
    # asked for).
    has_open_case: int = 0
    # Set by select_ticket_to_close when the target ticket is unambiguous (either the
    # customer named it explicitly, or it's the only open ticket of that kind). When the
    # customer has several of the same kind this stays None and every candidate is
    # proposed instead - see matching_open_tickets.
    target_ticket_id: str | None = None
    # Retained for historic traces and the audit record. Nothing routes on it any more:
    # the customer used to be asked WHICH ticket to close, because their answer performed
    # the close. Under the propose flow their answer would decide nothing, so the question
    # is no longer asked and every candidate is proposed to the agent instead.
    ticket_clarification_needed: bool = False
    # The tickets a proposal applies to. One when unambiguous; several when the customer
    # has multiple open cases of the same kind and the agent picks between them.
    matching_open_tickets: list[dict] = Field(default_factory=list)
    customer_validation: CustomerValidationResult = Field(default_factory=CustomerValidationResult)
    analysis: IntentResult | None = None
    resolution: QueryResolution | None = None
    ticket_decision: TicketDecision | None = None
    ticket: Ticket | None = None
    # True only when THIS message opened a new thread while other live threads existed -
    # i.e. the referee judged it a separate matter. A per-message fact, deliberately not
    # read from the ticket: `forked_from` is stored on the ticket and therefore persists
    # for its whole life, so reading that told a customer "this looks like a separate
    # issue" on every later message of a thread they were plainly continuing.
    ticket_forked_now: bool = False
    # Tickets this turn raised a close PROPOSAL on. Empty when the customer's words were
    # not a resolution, and also when every candidate was a `logged` grouping id (nothing
    # to close). Never means "closed" - a human decides that.
    close_proposed_ticket_ids: list[str] = Field(default_factory=list)
    answer: str | None = None
    delivery: dict = Field(default_factory=dict)
    workflow_trace: list[WorkflowTraceEntry] = Field(default_factory=list)
    inbound_turn_id: str | None = None
    # Human-in-the-loop: when the review gate holds the AI reply, ``answer`` is replaced by
    # the customer-facing holding message and the AI's real answer is stored as a reply_draft.
    held_for_review: bool = False
    draft_id: str | None = None

    @property
    def customer_id(self) -> str | None:
        return self.customer.get("customer_id") if self.customer else None

    @property
    def conversation_id(self) -> str | None:
        return self.conversation.get("conversation_id") if self.conversation else None

    def complete(self, step: WorkflowStep, agent: str, **details) -> None:
        self.workflow_trace.append(WorkflowTraceEntry(step=step, agent=agent, details=details))
