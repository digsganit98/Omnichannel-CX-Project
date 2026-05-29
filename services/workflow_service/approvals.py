def requires_approval(intent: str) -> bool:
    return intent in {"refund_request", "billing_issue"}
