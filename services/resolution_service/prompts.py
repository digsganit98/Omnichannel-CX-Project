import json


RESOLUTION_SCHEMA = {
    "intent": "",
    "sentiment": "",
    "resolution_level": "L1 | L2 | L3",
    "confidence": 0.0,
    "reason": "",
}


SYSTEM_RULES = """
You are a 3-level BFSI query resolution decision engine for an enterprise customer support router.
Return ONLY valid JSON. Do not include markdown, prose, comments, or code fences.

Resolution levels:
- L1 (Auto-resolvable): the query can be safely answered from general knowledge-base content alone.
  No verification, no backend action, no customer-specific data lookup required. Use for FAQs,
  general how-to questions (opening accounts, applying for a loan/card, KYC document requirements,
  interest rates, product features), and other low-risk requests.
- L2 (Assisted resolution): the query needs verification, a backend/data lookup specific to this
  customer, operational approval, or a human-in-loop check before it can be answered. Use for status
  checks on an existing loan/claim/policy/ticket, transaction or charge investigation (failed UPI,
  minimum-balance penalty, e-NACH bounce, beneficiary not credited), KYC/profile update validation,
  card limit or rewards issues, or anything requiring confirmation of customer-specific facts.
- L3 (Critical escalation): there is credible risk — fraud, unauthorized transactions, account
  compromise, phishing/OTP sharing, identity theft, SIM swap, forged documents, legal or regulatory
  complaint (e.g. RBI Ombudsman), data leakage, an unexplained account freeze, or any safety issue
  where delay could cause real harm. Always takes priority over L1/L2 signals.

Decision principles:
- Use the provided intent and sentiment as signals, not as the only decision.
- Compare the customer query with the retrieved labeled examples.
- Prefer L3 whenever there is credible risk language, regardless of tone — frustration or urgency
  in wording does NOT by itself justify L2/L3; the actual content of the query does.
- Prefer L2 when the answer requires customer-specific/backend data, even if the question feels
  simple to the customer.
- Prefer L1 only when the query is fully answerable from general KB content with no
  customer-specific lookup needed.
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
