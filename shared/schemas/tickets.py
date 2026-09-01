from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class TicketStatus(StrEnum):
    # A grouping id and nothing more: this thread exists, but no human is needed yet.
    # Splitting this out is the point of the ticket-model redesign - "is this a distinct
    # matter?" and "does a human need to see it?" were one boolean, so there was no way to
    # say "this is a thread, no human required", which is the common case.
    # A LOGGED ticket becomes OPEN the first time a message on it triggers a hold.
    LOGGED = "logged"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    # A finished case is CLOSED. "Resolution" in this repo means answering a query
    # (resolution_level, QueryResolution, ResolutionMemory, Interaction.resolution) -
    # a separate idea from a case being over, and conflating the two caused Fixes 87,
    # 88 and 90. The stored value is the word itself so nothing has to translate it:
    # a display-only mapping cannot reach inside LLM-generated text, which is how
    # "resolved" reached the agent's case summary.
    CLOSED = "closed"


# Every read site must say WHICH question it is asking. Before LOGGED existed there was
# only one question ("is it closed?"), so sites were written as `status != 'closed'` -
# a test defined by EXCLUSION, which admits any new value silently. That is exactly how a
# logging ticket would have reached the reply prompt while being invisible in the UI (the
# JS side asks the opposite, `status === 'open' || 'in_progress'`, and drops it). These
# tuples are inclusion lists: a new status is a compile-time-visible decision at each site,
# not a default.
#
# SERVICEABLE - a human is involved. Use for anything an AGENT should see or act on, and
#               for anything the customer may be told about.
# ACTIVE      - not finished. Use for grouping and continuity, where a logging thread
#               counts just as much as an escalated one.
SERVICEABLE_TICKET_STATUSES = (TicketStatus.OPEN, TicketStatus.IN_PROGRESS)
ACTIVE_TICKET_STATUSES = (TicketStatus.LOGGED, TicketStatus.OPEN, TicketStatus.IN_PROGRESS)


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
