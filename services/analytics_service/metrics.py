from dataclasses import dataclass, field


@dataclass
class OverviewMetrics:
    total_open: int = 0
    total_resolved: int = 0
    total_escalated: int = 0
    avg_resolution_minutes: float = 0.0
    sla_breach_count: int = 0
    total_conversations: int = 0
    total_customers: int = 0
    neg_sentiment_today_pct: float = 0.0
    neg_sentiment_yesterday_pct: float = 0.0
    avg_first_response_minutes: float = 0.0
    avg_first_response_last_week_minutes: float = 0.0


@dataclass
class ChannelCount:
    channel: str = ""
    ticket_count: int = 0
    message_count: int = 0


@dataclass
class ChannelMetrics:
    channels: list[ChannelCount] = field(default_factory=list)


@dataclass
class IntentCount:
    intent: str = ""
    count: int = 0


@dataclass
class IntentMetrics:
    intents: list[IntentCount] = field(default_factory=list)


@dataclass
class SentimentMetrics:
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    total: int = 0


@dataclass
class AgentMetrics:
    agent: str = ""
    handled: int = 0
    avg_handle_minutes: float = 0.0
    escalations: int = 0


@dataclass
class TicketTrendPoint:
    date: str = ""
    created: int = 0
    resolved: int = 0


@dataclass
class RealtimeEvent:
    event_id: str = ""
    event_type: str = ""
    channel: str = ""
    intent: str = ""
    customer_id: str = ""
    created_at: str = ""
