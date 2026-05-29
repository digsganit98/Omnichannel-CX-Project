from pydantic import BaseModel

from shared.schemas.messages import InboundMessage


class OrchestrationState(BaseModel):
    message: InboundMessage
    conversation_id: str
    intent: str = "general_question"
    sentiment: str = "neutral"
    urgency: str = "low"
    answer: str | None = None
    confidence: float = 0.0
    ticket_id: str | None = None
