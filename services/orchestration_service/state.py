from enum import StrEnum

from pydantic import BaseModel, Field

from services.agent_service.orchestration_agents import QueryResolution, TicketActionDecision, TicketDecision
from shared.schemas.intents import IntentResult
from shared.schemas.messages import InboundMessage
from shared.schemas.tickets import Ticket


class WorkflowStep(StrEnum):
    RECEIVE_MESSAGE = "receive_message"
    RESOLVE_IDENTITY = "resolve_identity"
    LOAD_CONVERSATION_CONTEXT = "load_conversation_context"
    DETECT_TICKET_ACTION = "detect_ticket_action"
    CLASSIFY_INTENT = "classify_intent"
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
    analysis: IntentResult | None = None
    resolution: QueryResolution | None = None
    ticket_decision: TicketDecision | None = None
    ticket: Ticket | None = None
    answer: str | None = None
    delivery: dict = Field(default_factory=dict)
    workflow_trace: list[WorkflowTraceEntry] = Field(default_factory=list)

    @property
    def customer_id(self) -> str | None:
        return self.customer.get("customer_id") if self.customer else None

    @property
    def conversation_id(self) -> str | None:
        return self.conversation.get("conversation_id") if self.conversation else None

    def complete(self, step: WorkflowStep, agent: str, **details) -> None:
        self.workflow_trace.append(WorkflowTraceEntry(step=step, agent=agent, details=details))
