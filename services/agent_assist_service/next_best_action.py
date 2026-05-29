def recommend_next_best_action(intent: str, sentiment: str, urgency: str, ticket_id: str | None) -> str:
    if ticket_id:
        return "Review context, validate customer details, and update the ticket with the next action."
    if intent == "refund_request":
        return "Check refund eligibility and offer policy-compliant options."
    if sentiment == "negative" or urgency != "low":
        return "Respond empathetically and monitor for escalation."
    return "Share the resolved answer and ask whether anything else is needed."
