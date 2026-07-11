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
    workflow_status: str | None = None
    analysis_source: str | None = None
    rag_contexts: list[dict] = Field(default_factory=list)
    llm_model: str | None = None
    llm_used: bool = False
    citations: list[dict] = Field(default_factory=list)
    retrieval_backend: str | None = None
    outbound_status: str = "pending"
    outbound_error: str | None = None
    duplicate: bool = False
    workflow_trace: list[dict] = Field(default_factory=list)
