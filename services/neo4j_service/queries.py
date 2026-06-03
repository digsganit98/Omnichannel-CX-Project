"""Intent-routed Neo4j query helpers for BFSI customer data."""

TRANSACTIONAL_INTENTS = {
    "loan_status",
    "loan_application",
    "loan_default_notice",
    "insurance_claim",
    "policy_status",
    "transaction_dispute",
    "account_balance_inquiry",
    "fund_transfer",
}


def get_customer_by_identifier(client, identifier: str) -> dict | None:
    """Look up customer by phone or email (channel identifier)."""
    rows = client.query(
        """
        MATCH (c:Customer)
        WHERE c.phone = $id OR c.email = $id OR c.secondary_email = $id
        RETURN c.customer_id AS customer_id, c.email AS email,
               c.phone AS phone, c.city AS city
        LIMIT 1
        """,
        {"id": identifier},
    )
    return rows[0] if rows else None


def get_loan_status(client, customer_id: str) -> list[dict]:
    return client.query(
        """
        MATCH (c:Customer {customer_id: $cid})-[:HAS_LOAN]->(l:Loan)
        RETURN l.loan_id AS loan_id, l.loan_type AS loan_type,
               l.status AS status, l.amount_inr AS amount_inr,
               l.interest_rate AS interest_rate, l.next_step AS next_step,
               l.last_updated AS last_updated
        """,
        {"cid": customer_id},
    )


def get_claim_status(client, customer_id: str) -> list[dict]:
    return client.query(
        """
        MATCH (c:Customer {customer_id: $cid})-[:HAS_CLAIM]->(cl:Claim)
        RETURN cl.claim_id AS claim_id, cl.policy_type AS policy_type,
               cl.claim_type AS claim_type, cl.status AS status,
               cl.amount_claimed_inr AS amount_claimed,
               cl.amount_approved_inr AS amount_approved,
               cl.reason AS reason, cl.last_updated AS last_updated
        """,
        {"cid": customer_id},
    )


def get_customer_context(client, channel_identifier: str) -> dict:
    """Return a rich context dict for LLM enrichment, looked up by phone/email."""
    customer = get_customer_by_identifier(client, channel_identifier)
    if not customer:
        return {}
    cid = customer["customer_id"]
    loans = get_loan_status(client, cid)
    claims = get_claim_status(client, cid)
    return {
        "customer_id": cid,
        "email": customer.get("email"),
        "phone": customer.get("phone"),
        "city": customer.get("city"),
        "loans": loans,
        "claims": claims,
    }


def neo4j_answer(client, intent: str, customer_id: str) -> str | None:
    """Return a formatted natural-language answer for transactional intents.

    Returns None for intents that should fall through to RAG.
    """
    if intent not in TRANSACTIONAL_INTENTS:
        return None

    if intent in {"loan_status", "loan_application", "loan_default_notice"}:
        loans = get_loan_status(client, customer_id)
        if not loans:
            return "No active loan records were found for your account."
        lines = ["Here is your loan summary:"]
        for l in loans:
            lines.append(
                f"  • {l['loan_type']} (ID: {l['loan_id']}): Status = {l['status']}, "
                f"Amount = ₹{l['amount_inr']:,}, Rate = {l['interest_rate']}%, "
                f"Next step: {l['next_step']}"
            )
        return "\n".join(lines)

    if intent in {"insurance_claim", "policy_status"}:
        claims = get_claim_status(client, customer_id)
        if not claims:
            return "No insurance claims or policies were found for your account."
        lines = ["Here is your claims summary:"]
        for c in claims:
            lines.append(
                f"  • Claim {c['claim_id']} ({c['policy_type']} / {c['claim_type']}): "
                f"Status = {c['status']}, Claimed = ₹{c['amount_claimed']:,}, "
                f"Approved = ₹{c['amount_approved']:,}. {c['reason']}"
            )
        return "\n".join(lines)

    # account_balance_inquiry / transaction_dispute / fund_transfer → no account table in xlsx
    return (
        "I can see your profile but detailed account balance and transaction history "
        "require live banking integration. A support specialist will assist you shortly."
    )
