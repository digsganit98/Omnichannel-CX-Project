from services.ticket_service.priority_scoring import score_priority
from shared.schemas.intents import Intent, Urgency
from shared.schemas.tickets import TicketPriority


def test_fraud_negative_high_urgency_hni_customer_is_critical():
    priority, breakdown = score_priority(
        Intent.FRAUD_REPORT,
        Urgency.HIGH,
        "negative",
        {"segment": "HNI"},
    )
    assert priority == TicketPriority.CRITICAL
    assert breakdown.total == breakdown.urgency_points + breakdown.sentiment_points \
        + breakdown.intent_criticality_points + breakdown.customer_value_points


def test_general_inquiry_positive_low_urgency_mass_customer_is_low():
    priority, breakdown = score_priority(
        Intent.GENERAL_INQUIRY,
        Urgency.LOW,
        "positive",
        {"segment": "Mass"},
    )
    assert priority == TicketPriority.LOW
    assert breakdown.customer_value_points == 0
    assert breakdown.sentiment_points == 0


def test_missing_graph_context_degrades_gracefully_to_zero_customer_value():
    priority, breakdown = score_priority(Intent.LOAN_STATUS, Urgency.MEDIUM, "neutral", None)
    assert breakdown.customer_value_points == 0
    assert priority in TicketPriority


def test_unknown_segment_degrades_gracefully_to_zero_customer_value():
    _, breakdown = score_priority(Intent.LOAN_STATUS, Urgency.MEDIUM, "neutral", {"segment": None})
    assert breakdown.customer_value_points == 0
