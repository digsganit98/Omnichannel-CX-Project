INTENT_TO_TEAM = {
    "account_balance_inquiry": "retail_banking",
    "transaction_dispute":     "fraud_and_disputes",
    "fund_transfer":           "payments",
    "loan_status":             "loans",
    "loan_application":        "loans",
    "loan_default_notice":     "collections",
    "policy_status":           "insurance_operations",
    "claim_status":            "claims",
    "insurance_claim":         "claims",
    "card_management":         "card_services",
    "kyc_update":              "compliance",
    "fraud_report":            "fraud_and_disputes",
    "complaint":               "customer_care",
    "ticket_status":           "customer_care",
    "general_inquiry":         "customer_care",
    "human_escalation":        "customer_care",
}

# 0-25 scale, used by services/ticket_service/priority_scoring.py as one signal
# in the overall priority score. Fraud/escalation intents score highest since
# they carry the most regulatory and customer-harm risk if delayed.
INTENT_CRITICALITY = {
    "fraud_report":            25,
    "human_escalation":        25,
    "transaction_dispute":     20,
    "loan_default_notice":     20,
    "insurance_claim":         15,
    "kyc_update":              15,
    "complaint":               12,
    "card_management":         10,
    "claim_status":            8,
    "fund_transfer":           8,
    "loan_application":        6,
    "policy_status":           4,
    "loan_status":             4,
    "account_balance_inquiry": 2,
    "ticket_status":           2,
    "general_inquiry":         0,
}
