def requires_approval(intent: str) -> bool:
    return intent in {
        "insurance_claim",
        "loan_application",
        "fund_transfer",
        "fraud_report",
        "loan_default_notice",
    }
