"""Intent-routed Neo4j query helpers for BFSI customer data."""

TRANSACTIONAL_INTENTS = {
    "loan_status",
    "loan_default_notice",
    "claim_status",
    "policy_status",
    "transaction_dispute",
    "account_balance_inquiry",
    "fund_transfer",
}


def get_customer_by_identifier(client, identifier: str) -> dict | None:
    """Look up customer by phone or email (channel identifier).

    Handles WhatsApp phone numbers that arrive with a country-code prefix
    (e.g. '919876510100') while the BFSI dataset stores bare 10-digit numbers
    ('9876510100').  Both formats are tried in a single query.
    """
    # Derive a stripped variant: remove a leading 2-digit country code when the
    # identifier is a 12-digit number starting with '91' (India).
    stripped = identifier[2:] if (len(identifier) == 12 and identifier.startswith("91")) else identifier
    rows = client.query(
        """
        MATCH (c:Customer)
        WHERE c.phone = $id OR c.phone = $stripped
           OR c.email = $id OR c.secondary_email = $id
        RETURN c.customer_id AS customer_id, c.email AS email,
               c.phone AS phone, c.city AS city,
               c.registration_date AS registration_date
        LIMIT 1
        """,
        {"id": identifier, "stripped": stripped},
    )
    return rows[0] if rows else None


def get_customer_by_id(client, customer_id: str) -> dict | None:
    rows = client.query(
        """
        MATCH (c:Customer {customer_id: $customer_id})
        RETURN c.customer_id AS customer_id, c.email AS email,
               c.phone AS phone, c.city AS city,
               c.registration_date AS registration_date
        LIMIT 1
        """,
        {"customer_id": customer_id},
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
    return get_customer_context_for_customer(client, customer)


def get_customer_context_by_id(client, customer_id: str) -> dict:
    """Return graph context for a known Neo4j customer_id."""
    customer = get_customer_by_id(client, customer_id)
    return get_customer_context_for_customer(client, customer)


def get_customer_context_for_customer(client, customer: dict | None) -> dict:
    """Return a rich context dict for an already resolved Neo4j customer."""
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


def _fmt_amount(value) -> str:
    """Safely format a currency amount that may be stored as int, float, or string."""
    try:
        return f"₹{int(float(str(value).replace(',', ''))):,}"
    except (ValueError, TypeError):
        return str(value) if value else "N/A"


def neo4j_answer(client, intent: str, customer_id: str) -> str | None:
    """Return a formatted natural-language answer for transactional intents.

    Returns None for intents that should fall through to RAG.
    """
    if intent not in TRANSACTIONAL_INTENTS:
        return None

    if intent in {"loan_status", "loan_default_notice"}:
        loans = get_loan_status(client, customer_id)
        if not loans:
            return "No active loan records were found for your account."
        lines = ["Here is your loan summary:"]
        for loan in loans:
            lines.append(
                f"  • {loan['loan_type']} (ID: {loan['loan_id']}): "
                f"Status = {loan['status']}, "
                f"Amount = {_fmt_amount(loan['amount_inr'])}, "
                f"Rate = {loan['interest_rate']}%, "
                f"Next step: {loan['next_step']}"
            )
        return "\n".join(lines)

    if intent in {"claim_status", "policy_status"}:
        claims = get_claim_status(client, customer_id)
        if not claims:
            return "No insurance claims or policies were found for your account."
        lines = ["Here is your claims summary:"]
        for claim in claims:
            approved = _fmt_amount(claim["amount_approved"]) if str(claim.get("amount_approved", "")).upper() != "N/A" else "Pending"
            lines.append(
                f"  • Claim {claim['claim_id']} ({claim['policy_type']} / {claim['claim_type']}): "
                f"Status = {claim['status']}, "
                f"Claimed = {_fmt_amount(claim['amount_claimed'])}, "
                f"Approved = {approved}. "
                f"{claim['reason']}"
            )
        return "\n".join(lines)

    # account_balance_inquiry / transaction_dispute / fund_transfer → no account table in xlsx
    return (
        "I can see your profile but detailed account balance and transaction history "
        "require live banking integration. A support specialist will assist you shortly."
    )
