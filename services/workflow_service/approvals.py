def requires_approval(intent: str) -> bool:
    return intent in {"refund_request", "return_request", "billing_issue"}
