"""Intent-routed Neo4j query helpers for BFSI customer data."""

# Intents where Neo4j has real customer data to return.
# account_balance_inquiry and fund_transfer excluded: no live banking integration.
# transaction_dispute excluded: no transactions table — neo4j_answer() always returned None
# for it, wasting a Neo4j round-trip before falling to RAG + MANUAL_REVIEW escalation.
TRANSACTIONAL_INTENTS = {
    "loan_status",
    "loan_default_notice",
    "claim_status",
    "policy_status",
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
               l.last_updated AS last_updated,
               l.emi_amount_inr AS emi_amount_inr,
               l.outstanding_principal_inr AS outstanding_principal_inr,
               l.next_emi_date AS next_emi_date,
               l.foreclosure_amount_inr AS foreclosure_amount_inr,
               l.emis_paid AS emis_paid,
               l.tenure_months AS tenure_months,
               l.dpd AS dpd,
               l.overdue_amount_inr AS overdue_amount_inr,
               l.penalty_inr AS penalty_inr,
               l.arrears_bucket AS arrears_bucket,
               l.collections_stage AS collections_stage,
               l.collateral_type AS collateral_type,
               l.collateral_value_inr AS collateral_value_inr,
               l.ltv_percent AS ltv_percent,
               l.sanctioned_amount_inr AS sanctioned_amount_inr,
               l.disbursed_amount_inr AS disbursed_amount_inr
        """,
        {"cid": customer_id},
    )


def get_policy_status(client, customer_id: str) -> list[dict]:
    try:
        return client.query(
            """
            MATCH (c:Customer {customer_id: $cid})-[:HAS_POLICY]->(p:Policy)
            RETURN p.policy_id AS policy_id, p.policy_type AS policy_type,
                   p.status AS status, p.premium_inr AS premium_inr,
                   p.coverage_inr AS coverage_inr,
                   p.maturity_date AS maturity_date,
                   p.next_premium_due AS next_premium_due,
                   p.premium_status AS premium_status,
                   p.overdue_premium_inr AS overdue_premium_inr,
                   p.late_fee_inr AS late_fee_inr,
                   p.grace_period_days AS grace_period_days,
                   p.premiums_paid AS premiums_paid
            """,
            {"cid": customer_id},
        )
    except Exception:
        return []


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
    policies = get_policy_status(client, cid)
    return {
        "customer_id": cid,
        "email": customer.get("email"),
        "phone": customer.get("phone"),
        "city": customer.get("city"),
        "loans": loans,
        "claims": claims,
        "policies": policies,
    }


def _fmt_amount(value) -> str:
    """Safely format a currency amount that may be stored as int, float, or string."""
    try:
        return f"Rs.{int(float(str(value).replace(',', ''))):,}"
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
            return None  # Fall through to RAG — PROMPT-5 handles the no-data response cleanly
        lines = ["Loan records:"]
        any_overdue = False
        for loan in loans:
            line = (
                f"  - {loan['loan_type']} (ID: {loan['loan_id']}): "
                f"Status: {loan['status']}, "
                f"Amount: {_fmt_amount(loan['amount_inr'])}, "
                f"Rate: {loan['interest_rate']}%, "
                f"Next step: {loan['next_step']}"
            )
            # Append EMI schedule details only for disbursed loans that have one.
            if loan.get("emi_amount_inr"):
                due = loan.get("next_emi_date")
                due_clause = f" due {due}" if due else ""
                line += (
                    f". EMI: {_fmt_amount(loan['emi_amount_inr'])}{due_clause}, "
                    f"Outstanding: {_fmt_amount(loan.get('outstanding_principal_inr', 0))}"
                )
                if loan.get("foreclosure_amount_inr"):
                    line += f", Foreclosure amount: {_fmt_amount(loan['foreclosure_amount_inr'])}"
            # Append collateral + disbursement details (item 17) where present.
            if loan.get("collateral_type"):
                ltv = loan.get("ltv_percent")
                ltv_clause = f", LTV {ltv}%" if ltv else ""
                line += (
                    f". Collateral: {loan['collateral_type']} "
                    f"({_fmt_amount(loan.get('collateral_value_inr', 0))}{ltv_clause})"
                )
            if loan.get("sanctioned_amount_inr"):
                line += (
                    f". Disbursed: {_fmt_amount(loan.get('disbursed_amount_inr', 0))} "
                    f"of {_fmt_amount(loan['sanctioned_amount_inr'])} sanctioned"
                )
            # Append arrears details when the loan is overdue (item 16).
            dpd = loan.get("dpd") or 0
            try:
                dpd = int(dpd)
            except (ValueError, TypeError):
                dpd = 0
            if dpd > 0:
                any_overdue = True
                line += (
                    f". Overdue: {_fmt_amount(loan.get('overdue_amount_inr', 0))} "
                    f"({dpd} days past due"
                    + (f", late fee {_fmt_amount(loan['penalty_inr'])}" if loan.get("penalty_inr") else "")
                    + ")"
                )
            lines.append(line)
        # For a default/overdue enquiry, lead with a factual, fair-practice summary
        # (no threatening language) before the per-loan records.
        if intent == "loan_default_notice":
            if any_overdue:
                header = (
                    "You have an overdue amount on one or more loans. Please clear the "
                    "overdue amount at the earliest to avoid additional charges and impact "
                    "to your credit score. Details below:"
                )
            else:
                header = "There is no overdue amount on record for your loans. Details below:"
            return header + "\n" + "\n".join(lines)
        return "\n".join(lines)

    if intent == "claim_status":
        claims = get_claim_status(client, customer_id)
        if not claims:
            return None  # Fall through to RAG
        lines = ["Claim records:"]
        for claim in claims:
            approved = _fmt_amount(claim["amount_approved"]) if str(claim.get("amount_approved", "")).upper() not in ("N/A", "NONE", "") else "Pending"
            lines.append(
                f"  - Claim {claim['claim_id']} ({claim['policy_type']} / {claim['claim_type']}): "
                f"Status: {claim['status']}, "
                f"Claimed: {_fmt_amount(claim['amount_claimed'])}, "
                f"Approved: {approved}. "
                f"{claim.get('reason', '')}"
            )
        return "\n".join(lines)

    if intent == "policy_status":
        # Try dedicated Policy nodes first; fall back to claim records if none exist.
        policies = get_policy_status(client, customer_id)
        if policies:
            lines = ["Policy records:"]
            for p in policies:
                maturity = f", Maturity: {p['maturity_date']}" if p.get("maturity_date") else ""
                next_due = f", Next premium due: {p['next_premium_due']}" if p.get("next_premium_due") else ""
                line = (
                    f"  - {p.get('policy_type', 'Policy')} (ID: {p.get('policy_id', '')}): "
                    f"Status: {p.get('status', 'Unknown')}, "
                    f"Coverage: {_fmt_amount(p.get('coverage_inr', 0))}, "
                    f"Premium: {_fmt_amount(p.get('premium_inr', 0))}"
                    f"{maturity}{next_due}"
                )
                # Item 12: premium payment history — flag overdue premiums factually
                # (fair-practice; mention the grace period so the message is helpful).
                if str(p.get("premium_status", "")).lower() == "overdue" and p.get("overdue_premium_inr"):
                    grace = p.get("grace_period_days")
                    grace_clause = f" (grace period {grace} days)" if grace else ""
                    late = p.get("late_fee_inr")
                    late_clause = f", late fee {_fmt_amount(late)}" if late else ""
                    line += (
                        f". Premium overdue: {_fmt_amount(p['overdue_premium_inr'])}"
                        f"{late_clause}{grace_clause} — please pay to keep the policy active"
                    )
                lines.append(line)
            return "\n".join(lines)
        # No Policy nodes — check if claim data gives partial context
        claims = get_claim_status(client, customer_id)
        if claims:
            lines = ["Insurance records (claims on file):"]
            for claim in claims:
                lines.append(
                    f"  - {claim['policy_type']} policy / {claim['claim_type']} "
                    f"(Claim ID: {claim['claim_id']}): Status: {claim['status']}, "
                    f"Claimed: {_fmt_amount(claim['amount_claimed'])}"
                )
            return "\n".join(lines)
        return None  # Fall through to RAG

    # transaction_dispute → no transaction table; returns None → RAG → Rule 2 still fires (MANUAL_REVIEW)
    return None
