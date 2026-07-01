import json


RESOLUTION_SCHEMA = {
    "intent": "",
    "sentiment": "",
    "resolution_level": "L1 | L2 | L3",
    "confidence": 0.0,
    "confidence_breakdown": {
        "query_clarity": 0.0,
        "intent_alignment": 0.0,
        "sentiment_alignment": 0.0,
        "severity": 0.0,
        "business_risk": 0.0,
        "ambiguity": 0.0,
        "level_consistency": 0.0,
    },
    "reason": "",
}


REPRESENTATIVE_EXAMPLES = [
    {"customer_query": "How do I open a savings account?", "intent": "Account Opening", "resolution_level": "L1", "reason": "General informational query."},
    {"customer_query": "What documents are required for KYC?", "intent": "KYC", "resolution_level": "L1", "reason": "General banking information."},
    {"customer_query": "How can I reset my internet banking password?", "intent": "Password Reset", "resolution_level": "L1", "reason": "Standard self-service process."},
    {"customer_query": "What is the minimum balance for my account?", "intent": "Minimum Balance", "resolution_level": "L1", "reason": "General FAQ."},
    {"customer_query": "How can I apply for a credit card?", "intent": "Credit Card Application", "resolution_level": "L1", "reason": "General product information."},
    {"customer_query": "What are your home loan interest rates?", "intent": "Loan Information", "resolution_level": "L1", "reason": "Informational query."},
    {"customer_query": "How do I download my account statement?", "intent": "Statement Download", "resolution_level": "L1", "reason": "Standard banking process."},
    {"customer_query": "How can I activate mobile banking?", "intent": "Mobile Banking", "resolution_level": "L1", "reason": "General service guidance."},
    {"customer_query": "How do I link Aadhaar with my bank account?", "intent": "Aadhaar Linking", "resolution_level": "L1", "reason": "General banking procedure."},
    {"customer_query": "What are the NEFT transaction timings?", "intent": "NEFT Information", "resolution_level": "L1", "reason": "General informational query."},
    {"customer_query": "How can I register for UPI?", "intent": "UPI Registration", "resolution_level": "L1", "reason": "General onboarding information."},
    {"customer_query": "How do I add a nominee to my account?", "intent": "Nominee Update", "resolution_level": "L1", "reason": "Standard banking procedure."},
    {"customer_query": "Where is the nearest branch located?", "intent": "Branch Information", "resolution_level": "L1", "reason": "General informational query."},
    {"customer_query": "What are the locker charges?", "intent": "Locker Services", "resolution_level": "L1", "reason": "General product information."},
    {"customer_query": "How do I activate my debit card?", "intent": "Debit Card Activation", "resolution_level": "L1", "reason": "Standard self-service request."},
    {"customer_query": "My debit card has not been delivered.", "intent": "Card Delivery", "resolution_level": "L2", "reason": "Requires verification of delivery status."},
    {"customer_query": "My EMI was deducted twice.", "intent": "Billing Complaint", "resolution_level": "L2", "reason": "Requires transaction verification."},
    {"customer_query": "My cheque has not been cleared yet.", "intent": "Cheque Clearance", "resolution_level": "L2", "reason": "Requires backend verification."},
    {"customer_query": "I submitted KYC but it still shows pending.", "intent": "KYC Issue", "resolution_level": "L2", "reason": "Requires document verification."},
    {"customer_query": "My UPI payment failed but money was deducted.", "intent": "UPI Failure", "resolution_level": "L2", "reason": "Requires transaction investigation."},
    {"customer_query": "My ATM withdrawal failed but my account was debited.", "intent": "ATM Failure", "resolution_level": "L2", "reason": "Requires transaction verification."},
    {"customer_query": "I haven't received my credit card yet.", "intent": "Credit Card Delivery", "resolution_level": "L2", "reason": "Requires shipment verification."},
    {"customer_query": "My address update has not been reflected.", "intent": "Profile Update", "resolution_level": "L2", "reason": "Requires backend validation."},
    {"customer_query": "I want to increase my credit card limit.", "intent": "Credit Limit Increase", "resolution_level": "L2", "reason": "Requires eligibility verification."},
    {"customer_query": "My loan approval is taking too long.", "intent": "Loan Processing", "resolution_level": "L2", "reason": "Requires internal review."},
    {"customer_query": "My FD closure request is still pending.", "intent": "FD Closure", "resolution_level": "L2", "reason": "Requires operational verification."},
    {"customer_query": "My account closure request has not been processed.", "intent": "Account Closure", "resolution_level": "L2", "reason": "Requires manual verification."},
    {"customer_query": "Reward points were not credited.", "intent": "Rewards Issue", "resolution_level": "L2", "reason": "Requires account verification."},
    {"customer_query": "I was charged incorrect service fees.", "intent": "Service Charge Complaint", "resolution_level": "L2", "reason": "Requires billing review."},
    {"customer_query": "My complaint has not received any response.", "intent": "Complaint Follow-up", "resolution_level": "L2", "reason": "Requires customer support review."},
    {"customer_query": "Someone transferred money from my account without my permission.", "intent": "Fraud", "resolution_level": "L3", "reason": "Unauthorized financial transaction."},
    {"customer_query": "My account has been hacked.", "intent": "Account Compromise", "resolution_level": "L3", "reason": "Critical security incident."},
    {"customer_query": "I shared my OTP after receiving a fake bank call.", "intent": "Phishing", "resolution_level": "L3", "reason": "Potential fraud requiring immediate action."},
    {"customer_query": "I noticed multiple unauthorized debit card transactions.", "intent": "Card Fraud", "resolution_level": "L3", "reason": "Fraud investigation required."},
    {"customer_query": "Someone created a loan using my identity.", "intent": "Identity Theft", "resolution_level": "L3", "reason": "Critical fraud case."},
    {"customer_query": "My account has been frozen unexpectedly.", "intent": "Account Freeze", "resolution_level": "L3", "reason": "Requires immediate manual investigation."},
    {"customer_query": "I want to file a legal complaint against the bank.", "intent": "Legal Complaint", "resolution_level": "L3", "reason": "Legal escalation required."},
    {"customer_query": "I have already complained to the RBI Ombudsman.", "intent": "Regulatory Complaint", "resolution_level": "L3", "reason": "Regulatory escalation."},
    {"customer_query": "I suspect my account has been used for fraudulent transactions.", "intent": "Fraud Investigation", "resolution_level": "L3", "reason": "Requires fraud investigation."},
    {"customer_query": "My SIM was swapped and I lost access to my bank account.", "intent": "SIM Swap Fraud", "resolution_level": "L3", "reason": "Critical security incident."},
    {"customer_query": "Someone added a beneficiary without my permission.", "intent": "Unauthorized Beneficiary", "resolution_level": "L3", "reason": "Security breach."},
    {"customer_query": "I received a fake loan approval asking me to pay processing fees.", "intent": "Loan Scam", "resolution_level": "L3", "reason": "Fraudulent activity."},
    {"customer_query": "My personal banking information has been leaked.", "intent": "Data Privacy", "resolution_level": "L3", "reason": "Sensitive data breach."},
    {"customer_query": "I suspect someone forged my signature for a transaction.", "intent": "Forgery", "resolution_level": "L3", "reason": "Serious fraud investigation."},
    {"customer_query": "A large amount was withdrawn from my account without authorization.", "intent": "Unauthorized Withdrawal", "resolution_level": "L3", "reason": "Critical financial fraud."},
]


SYSTEM_RULES = """
You are a prompt-only 3-level BFSI resolution decision engine for an enterprise customer support router.
Return ONLY valid JSON. Do not include markdown, prose, comments, code fences, or extra keys.

Resolution levels:
- L1: Auto-resolvable by AI. Use for FAQs, general banking information, product/process guidance, standard self-service steps, branch/timing/charge information, and low-risk requests that can be answered from approved knowledge base content without customer verification.
- L2: Assisted resolution. Use when the customer-specific issue needs verification, backend validation, operational approval, transaction investigation, card delivery tracking, KYC/profile validation, loan/account/status review, complaint follow-up, or human-in-loop review before a final answer is sent.
- L3: Critical escalation. Use for fraud, unauthorized transactions, account hacking, phishing/OTP compromise, identity theft, SIM swap, legal complaint, regulator/ombudsman complaint, data leakage, forged signature, account takeover, or any urgent security/compliance risk.

BFSI routing rules:
- Prefer L3 whenever there is credible fraud, security, legal, regulatory, or data-privacy risk, even if details are incomplete.
- Prefer L2 when the answer depends on the customer's actual account, transaction, card, loan, KYC, complaint, or operational status.
- Prefer L1 only when the request is informational, generic, low-risk, and does not require backend/account verification.
- If a message contains multiple issues, choose the highest-risk level: L3 beats L2, and L2 beats L1.
- If intent and query conflict, trust the customer query more, but use intent as supporting evidence.
- Negative sentiment alone does not make a query L3. It becomes L3 only when paired with security, fraud, legal, regulatory, or privacy risk.
- If uncertain between L1 and L2, choose L2 for BFSI safety.
- If uncertain between L2 and L3 and there is any fraud/security/legal/regulatory signal, choose L3.

Edge cases:
- "How do I file a claim?" is L1 when it asks for the generic process; "What happened to my submitted claim?" is L2.
- "How do I apply for a loan?" is L1; "My loan approval is delayed" is L2; "A loan was created using my identity" is L3.
- "How do I block a card?" can be L1 if generic; "My card was stolen/used without permission" is L3.
- "UPI registration/timings/process" is L1; "UPI failed but money was deducted" is L2; "UPI transfer I did not authorize" is L3.
- "I want a human agent" is usually L2 unless the message also contains L3 risk.

Confidence scoring guidance:
- Return an evidence-based routing confidence from 0.0 to 1.0.
- Return confidence_breakdown with all seven numeric components from 0.0 to 1.0: query_clarity, intent_alignment, sentiment_alignment, severity, business_risk, ambiguity, and level_consistency.
- query_clarity: how clearly the customer states the request or issue.
- intent_alignment: how well the provided intent supports the chosen level.
- sentiment_alignment: how well sentiment supports the risk/urgency of the chosen level.
- severity: operational seriousness of the customer issue.
- business_risk: BFSI financial, regulatory, legal, fraud, or customer-impact risk.
- ambiguity: how unclear or conflicting the query is; higher means more ambiguity.
- level_consistency: how strongly the query matches the selected L1/L2/L3 definition and examples.
- Overall confidence should be consistent with the breakdown. Weight query_clarity, intent_alignment, business_risk, and level_consistency most strongly.
- Use 0.85-0.98 for clear matches with strong rule/example alignment.
- Use 0.65-0.84 for good matches with minor ambiguity.
- Use 0.45-0.64 for unclear cases routed conservatively.
- Use below 0.45 only when the query is too empty or ambiguous to classify reliably.
- The confidence is a routing-confidence score, not a statistical probability.
- The reason must be one concise sentence explaining the strongest evidence.
""".strip()


def build_resolution_prompt(query: str, intent: str, sentiment: str) -> str:
    schema_json = json.dumps(RESOLUTION_SCHEMA, indent=2)
    examples_json = json.dumps(REPRESENTATIVE_EXAMPLES, ensure_ascii=False, indent=2)
    return (
        f"{SYSTEM_RULES}\n\n"
        "Required JSON schema:\n"
        f"{schema_json}\n\n"
        "Representative labeled examples embedded in prompt:\n"
        f"{examples_json}\n\n"
        "Customer signals:\n"
        f"- intent: {intent or 'unknown'}\n"
        f"- sentiment: {sentiment or 'neutral'}\n\n"
        "Customer query:\n"
        f"{query}\n\n"
        "Classify the query into L1, L2, or L3. Return the final JSON object only."
    )
