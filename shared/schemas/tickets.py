from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
