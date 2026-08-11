from __future__ import annotations

from pydantic import BaseModel

from shared.constants.intents import INTENT_CRITICALITY
from shared.constants.priority_weights import (
    CUSTOMER_VALUE_POINTS,
    PRIORITY_THRESHOLDS,
    SENTIMENT_POINTS,
    URGENCY_POINTS,
)
from shared.schemas.intents import Intent, Urgency
from shared.schemas.tickets import TicketPriority


class PriorityScoreBreakdown(BaseModel):
    urgency_points: float
    sentiment_points: float
    intent_criticality_points: float
    customer_value_points: float
    total: float


def score_priority(
    intent: Intent,
    urgency: Urgency,
    sentiment: str,
    graph_context: dict | None,
) -> tuple[TicketPriority, PriorityScoreBreakdown]:
    urgency_points = URGENCY_POINTS.get(urgency.value, 0)
    sentiment_points = SENTIMENT_POINTS.get(sentiment, 0)
    intent_criticality_points = INTENT_CRITICALITY.get(intent.value, 0)
    customer_value_points = CUSTOMER_VALUE_POINTS.get((graph_context or {}).get("segment"), 0)

    total = urgency_points + sentiment_points + intent_criticality_points + customer_value_points
    breakdown = PriorityScoreBreakdown(
        urgency_points=urgency_points,
        sentiment_points=sentiment_points,
        intent_criticality_points=intent_criticality_points,
        customer_value_points=customer_value_points,
        total=total,
    )

    if total >= PRIORITY_THRESHOLDS["critical"]:
        priority = TicketPriority.CRITICAL
    elif total >= PRIORITY_THRESHOLDS["high"]:
        priority = TicketPriority.HIGH
    elif total >= PRIORITY_THRESHOLDS["medium"]:
        priority = TicketPriority.MEDIUM
    else:
        priority = TicketPriority.LOW

    return priority, breakdown
