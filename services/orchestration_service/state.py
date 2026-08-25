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
    DETECT_TICKET_ACTION = "detect_ticket_action"
    CHECK_HAS_TICKET = "check_has_ticket"
    SELECT_TICKET_TO_RESOLVE = "select_ticket_to_resolve"
    CLASSIFY_INTENT = "classify_intent"
    VALIDATE_CUSTOMER = "validate_customer"
    REJECT_UNREGISTERED_CUSTOMER = "reject_unregistered_customer"
    RETRIEVE_KNOWLEDGE = "retrieve_knowledge"
    DECIDE_RESOLUTION = "decide_resolution"
    CREATE_OR_UPDATE_TICKET = "create_or_update_ticket"
    RESOLVE_TICKET = "resolve_ticket"
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
    # Binary flag set by the check_has_ticket node: 1 when this turn is a ticket-resolution
    # action (routes into the ticket branch), 0 otherwise (routes into the Agent 1 chain).
    has_ticket: int = 0
    # Set by select_ticket_to_resolve once the target ticket is unambiguous (either the
    # customer named it explicitly, or it's the only open ticket of that kind).
    target_ticket_id: str | None = None
    # True when the customer has 2+ open tickets of the same kind and didn't name one —
    # resolve_ticket is skipped and the customer is asked to specify which ticket.
    ticket_clarification_needed: bool = False
    # Candidate tickets considered during disambiguation, for audit/trace visibility.
    matching_open_tickets: list[dict] = Field(default_factory=list)
    customer_validation: CustomerValidationResult = Field(default_factory=CustomerValidationResult)
    analysis: IntentResult | None = None
    resolution: QueryResolution | None = None
    ticket_decision: TicketDecision | None = None
    ticket: Ticket | None = None
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
