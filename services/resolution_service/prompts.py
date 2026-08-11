import json


RESOLUTION_SCHEMA = {
    "intent": "",
    "sentiment": "",
    "resolution_level": "L1 | L2 | L3",
    "confidence": 0.0,
    "reason": "",
}


SYSTEM_RULES = """
You are a 3-level BFSI resolution decision engine for an enterprise customer support router.
Return ONLY valid JSON. Do not include markdown, prose, comments, or code fences.

Resolution levels:
- L1: Auto-resolvable by AI using the knowledge base. Use for FAQs, simple banking queries, general help, account/product information, and low-risk requests that do not require identity verification or backend action.
- L2: Assisted resolution. Use when the customer needs verification, backend validation, operational approval, transaction investigation, card delivery tracking, loan/account status review, KYC/profile validation, or human-in-loop checks.
- L3: Critical escalation. Use for fraud, unauthorized transactions, account hacking, phishing, identity theft, legal complaints, regulatory/compliance issues, data leakage, or immediate security risk.

Decision principles:
- Use the provided intent and sentiment as signals, not as the only decision.
- Compare the customer query with the retrieved labeled examples.
- Prefer L3 when there is credible fraud, security, legal, regulatory, or safety risk.
- Prefer L2 when customer-specific data or verification is required.
- Prefer L1 only when the query can be safely answered from general KB content.
- Confidence must be a number from 0.0 to 1.0.
- The reason must be one concise sentence.
""".strip()


def build_resolution_prompt(
    query: str,
    intent: str,
    sentiment: str,
    retrieved_examples: list[dict],
) -> str:
    examples_json = json.dumps(retrieved_examples, ensure_ascii=False, indent=2)
    schema_json = json.dumps(RESOLUTION_SCHEMA, indent=2)
    return (
        f"{SYSTEM_RULES}\n\n"
        "Required JSON schema:\n"
        f"{schema_json}\n\n"
        "Retrieved labeled examples (most similar first):\n"
        f"{examples_json or '[]'}\n\n"
        "Customer signals:\n"
        f"- intent: {intent or 'unknown'}\n"
        f"- sentiment: {sentiment or 'neutral'}\n\n"
        "Customer query:\n"
        f"{query}\n\n"
        "Return the final decision JSON only."
    )
