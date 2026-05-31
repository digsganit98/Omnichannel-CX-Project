from pydantic import BaseModel, Field


class ChannelResponse(BaseModel):
    correlation_id: str
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
    analysis_source: str | None = None
    rag_contexts: list[dict] = Field(default_factory=list)
    llm_model: str | None = None
    llm_used: bool = False
    citations: list[dict] = Field(default_factory=list)
    outbound_status: str = "pending"
    duplicate: bool = False
