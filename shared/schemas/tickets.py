from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    # A finished case is CLOSED. "Resolution" in this repo means answering a query
    # (resolution_level, QueryResolution, ResolutionMemory, Interaction.resolution) -
    # a separate idea from a case being over, and conflating the two caused Fixes 87,
    # 88 and 90. The stored value is the word itself so nothing has to translate it:
    # a display-only mapping cannot reach inside LLM-generated text, which is how
    # "resolved" reached the agent's case summary.
    CLOSED = "closed"


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Ticket(BaseModel):
    ticket_id: str
    conversation_id: str
    customer_id: str
    title: str
    description: str
    intent: str
    priority: TicketPriority
    assigned_team: str
    status: TicketStatus = TicketStatus.OPEN
    external_ticket_id: str | None = None
    external_ticket_url: str | None = None
    crm_sync_status: str = "not_configured"
    crm_sync_error: str | None = None
    approval_status: str = "not_required"
    escalation_reason: str | None = None
    sla_due_at: datetime | None = None
    priority_score: float = 0.0
    priority_breakdown: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
