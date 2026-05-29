from pydantic import BaseModel


class ChannelResponse(BaseModel):
    conversation_id: str
    customer_id: str
    message: str
    resolved: bool
    intent: str
    sentiment: str
    urgency: str
    confidence: float
    ticket_id: str | None = None
    next_best_action: str | None = None
