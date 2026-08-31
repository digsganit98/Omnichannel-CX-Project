"""Intent-routed Neo4j query helpers for BFSI customer data."""

# Intents where Neo4j has real customer data to return.
# fund_transfer excluded: no live payments integration.
# account_balance_inquiry answers from the graph's account/FD records (demo data, not a
# live banking feed) so card/account/FD questions return real figures instead of escalating.
# transaction_dispute WAS excluded on the stated grounds of "no transactions table". That
# was wrong: the seed loads a Transaction node per row of the Transactions sheet (72 for the
# 5 demo customers), including real failure states such as 'Debited-Pending-Credit' with a
# reason. The exclusion meant the single most common inbound intent answered from the generic
# KB while the customer's own disputed transaction sat unread in the graph.
TRANSACTIONAL_INTENTS = {
    "loan_status",
    "loan_default_notice",
    "claim_status",
    "policy_status",
    "card_management",
    "account_balance_inquiry",
    "transaction_dispute",
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
               c.registration_date AS registration_date,
               c.name AS name, c.age AS age, c.gender AS gender,
               c.occupation AS occupation, c.income_level AS income_level,
               c.segment AS segment
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
               c.registration_date AS registration_date,
               c.name AS name, c.age AS age, c.gender AS gender,
               c.occupation AS occupation, c.income_level AS income_level,
               c.segment AS segment
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


def get_policy_status(client, customer_id: str) -> list[dict]:
    try:
        return client.query(
            """
            MATCH (c:Customer {customer_id: $cid})-[:HAS_POLICY]->(p:Policy)
            RETURN p.policy_id AS policy_id, p.policy_type AS policy_type,
                   p.status AS status, p.premium_inr AS premium_inr,
                   p.coverage_inr AS coverage_inr,
                   p.maturity_date AS maturity_date,
                   p.next_premium_due AS next_premium_due
            """,
            {"cid": customer_id},
        )
    except Exception:
        return []


def get_accounts(client, customer_id: str) -> list[dict]:
    return client.query(
        """
        MATCH (c:Customer {customer_id: $cid})-[:HAS_ACCOUNT]->(a:Account)
        RETURN a.account_number AS account_number, a.account_category AS account_category,
               a.account_type AS account_type, a.account_sub_type AS account_sub_type,
               a.status AS status, a.avg_monthly_balance AS avg_monthly_balance,
               a.min_balance_required AS min_balance_required, a.branch AS branch,
               a.ifsc AS ifsc
        """,
        {"cid": customer_id},
    )


def get_credit_cards(client, customer_id: str) -> list[dict]:
    return client.query(
        """
        MATCH (c:Customer {customer_id: $cid})-[:HAS_CREDIT_CARD]->(cc:CreditCard)
        RETURN cc.card_id AS card_id, cc.card_network AS card_network,
               cc.card_variant AS card_variant, cc.credit_limit AS credit_limit,
               cc.balance_due AS balance_due, cc.min_amount_due AS min_amount_due,
               cc.total_amount_due AS total_amount_due, cc.payment_due_date AS payment_due_date,
               cc.dpd AS dpd, cc.penalty_details AS penalty_details,
               cc.reward_points_balance AS reward_points_balance,
               cc.chargeback_flag AS chargeback_flag, cc.fraud_flag AS fraud_flag,
               cc.fraud_type AS fraud_type
        """,
        {"cid": customer_id},
    )


def get_fixed_deposits(client, customer_id: str) -> list[dict]:
    return client.query(
        """
        MATCH (c:Customer {customer_id: $cid})-[:HAS_FD]->(fd:FixedDeposit)
        RETURN fd.fd_id AS fd_id, fd.principal_amount AS principal_amount,
               fd.interest_rate AS interest_rate, fd.tenure_months AS tenure_months,
               fd.maturity_date AS maturity_date, fd.maturity_amount AS maturity_amount,
               fd.status AS status
        """,
        {"cid": customer_id},
    )


def get_transactions(client, customer_id: str, limit: int = 20) -> list[dict]:
    return client.query(
        """
        MATCH (c:Customer {customer_id: $cid})-[:HAS_TRANSACTION]->(t:Transaction)
        RETURN t.txn_id AS txn_id, t.txn_date AS txn_date, t.amount AS amount,
               t.txn_type AS txn_type, t.channel AS channel, t.status AS status,
               t.beneficiary_name AS beneficiary_name, t.failure_reason AS failure_reason,
               t.narration AS narration
        ORDER BY t.txn_date DESC
        LIMIT $limit
        """,
        {"cid": customer_id, "limit": limit},
    )


def get_charges(client, customer_id: str) -> list[dict]:
    return client.query(
        """
        MATCH (c:Customer {customer_id: $cid})-[:HAS_CHARGE]->(ch:ChargePenalty)
        RETURN ch.charge_id AS charge_id, ch.charge_type AS charge_type,
               ch.amount AS amount, ch.charge_date AS charge_date,
               ch.reason AS reason, ch.reversal_status AS reversal_status
        """,
        {"cid": customer_id},
    )


def get_claim_status(client, customer_id: str) -> list[dict]:
    return client.query(
        """
        MATCH (c:Customer {customer_id: $cid})-[:HAS_CLAIM]->(cl:Claim)
        OPTIONAL MATCH (p:Policy)-[:HAS_CLAIM]->(cl)
        RETURN cl.claim_id AS claim_id, p.policy_type AS policy_type,
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


def get_open_cases(client, customer_id: str, limit: int = 5) -> list[dict]:
    """The customer's unresolved support cases, newest first.

    Deliberately bounded and summary-only. The conversation history the LLM receives is
    a fixed window of recent turns, so a case raised earlier simply scrolls out of view
    and the model stops knowing it exists — even though the ticket is still open. A case
    is a durable FACT about the customer, like a card limit, so it belongs in the trusted
    account context rather than depending on luck of the window.
    """
    if client is None or not customer_id:
        return []
    try:
        return client.query(
            """
            MATCH (c:Customer {customer_id: $cid})-[:HAS_TICKET]->(t:Ticket)
            WHERE t.status IS NULL OR t.status <> 'closed'
            RETURN t.ticket_id AS ticket_id, t.intent AS intent, t.status AS status,
                   t.priority AS priority, t.scope AS scope, t.title AS title
            ORDER BY t.ticket_id DESC
            LIMIT $limit
            """,
            {"cid": customer_id, "limit": limit},
        )
    except Exception:
        return []


def get_case_messages(client, ticket_id: str, limit: int = 4) -> list[dict]:
    """The messages attached to one ticket, newest first (see writer.link_interaction_to_ticket).

    Only exists because Interactions are now written per message and linked to their
    ticket; before that the graph held one node per conversation holding the newest
    sentence, so "the messages of this case" was not answerable.
    """
    if client is None or not ticket_id:
        return []
    try:
        return client.query(
            """
            MATCH (t:Ticket {ticket_id: $tid})-[:HAS_MESSAGE]->(i:Interaction)
            RETURN i.turn_id AS turn_id, i.message AS message, i.channel AS channel,
                   i.created_at AS created_at, i.status AS status
            ORDER BY i.created_at DESC
            LIMIT $limit
            """,
            {"tid": ticket_id, "limit": limit},
        )
    except Exception:
        return []


def get_customer_context_for_customer(client, customer: dict | None) -> dict:
    """Return a rich context dict for an already resolved Neo4j customer."""
    if not customer:
        return {}
    cid = customer["customer_id"]
    loans = get_loan_status(client, cid)
    claims = get_claim_status(client, cid)
    policies = get_policy_status(client, cid)
    credit_cards = get_credit_cards(client, cid)
    accounts = get_accounts(client, cid)
    fixed_deposits = get_fixed_deposits(client, cid)
    open_cases = get_open_cases(client, cid)
    return {
        "customer_id": cid,
        "name": customer.get("name"),
        "email": customer.get("email"),
        "phone": customer.get("phone"),
        "city": customer.get("city"),
        "segment": customer.get("segment"),
        "loans": loans,
        "claims": claims,
        "policies": policies,
        "credit_cards": credit_cards,
        "accounts": accounts,
        "fixed_deposits": fixed_deposits,
        "open_cases": open_cases,
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
        for loan in loans:
            lines.append(
                f"  - {loan['loan_type']} (ID: {loan['loan_id']}): "
                f"Status: {loan['status']}, "
                f"Amount: {_fmt_amount(loan['amount_inr'])}, "
                f"Rate: {loan['interest_rate']}%, "
                f"Next step: {loan['next_step']}"
            )
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
                lines.append(
                    f"  - {p.get('policy_type', 'Policy')} (ID: {p.get('policy_id', '')}): "
                    f"Status: {p.get('status', 'Unknown')}, "
                    f"Coverage: {_fmt_amount(p.get('coverage_inr', 0))}, "
                    f"Premium: {_fmt_amount(p.get('premium_inr', 0))}"
                    f"{maturity}{next_due}"
                )
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

    if intent == "card_management":
        cards = get_credit_cards(client, customer_id)
        if not cards:
            return None  # Fall through to RAG
        lines = ["Credit card records:"]
        for cc in cards:
            due = f", Total due: {_fmt_amount(cc['total_amount_due'])}" if cc.get("total_amount_due") not in (None, "") else ""
            min_due = f", Min due: {_fmt_amount(cc['min_amount_due'])}" if cc.get("min_amount_due") not in (None, "") else ""
            due_date = f", Payment due date: {cc['payment_due_date']}" if cc.get("payment_due_date") else ""
            lines.append(
                f"  - {cc.get('card_network', 'Card')} {cc.get('card_variant', '')} "
                f"(ID: {cc.get('card_id', '')}): "
                f"Credit limit: {_fmt_amount(cc.get('credit_limit'))}, "
                f"Balance due: {_fmt_amount(cc.get('balance_due'))}"
                f"{min_due}{due}{due_date}"
            )
        return "\n".join(lines)

    if intent == "account_balance_inquiry":
        # Surface both deposit accounts and fixed deposits — "balance" and
        # "FD details" questions both land on this intent.
        accounts = get_accounts(client, customer_id)
        fds = get_fixed_deposits(client, customer_id)
        if not accounts and not fds:
            return None  # Fall through to RAG
        lines = []
        if accounts:
            lines.append("Account records:")
            for a in accounts:
                lines.append(
                    f"  - {a.get('account_type', 'Account')} {a.get('account_sub_type', '')} "
                    f"(No: {a.get('account_number', '')}): "
                    f"Status: {a.get('status', 'Unknown')}, "
                    f"Avg monthly balance: {_fmt_amount(a.get('avg_monthly_balance'))}, "
                    f"Min balance required: {_fmt_amount(a.get('min_balance_required'))}"
                )
        if fds:
            lines.append("Fixed deposit records:")
            for fd in fds:
                maturity = f", Maturity date: {fd['maturity_date']}" if fd.get("maturity_date") else ""
                maturity_amt = f", Maturity amount: {_fmt_amount(fd['maturity_amount'])}" if fd.get("maturity_amount") not in (None, "") else ""
                lines.append(
                    f"  - FD {fd.get('fd_id', '')}: "
                    f"Principal: {_fmt_amount(fd.get('principal_amount'))}, "
                    f"Rate: {fd.get('interest_rate', 'N/A')}%, "
                    f"Tenure: {fd.get('tenure_months', 'N/A')} months, "
                    f"Status: {fd.get('status', 'Unknown')}"
                    f"{maturity}{maturity_amt}"
                )
        return "\n".join(lines)

    if intent == "transaction_dispute":
        # Most recent transactions, newest first (get_transactions orders by date DESC).
        # Capped at 8: a dispute is nearly always about a recent debit, and the whole block
        # is pasted into the prompt — 20 rows would crowd out the customer's actual question.
        # Failed/pending rows are surfaced explicitly because they are what a dispute is
        # usually about, and the seed carries real ones ('Debited-Pending-Credit' with a
        # reason), which a generic KB answer cannot mention.
        transactions = get_transactions(client, customer_id, limit=8)
        if not transactions:
            return None  # Fall through to RAG
        lines = ["Recent transaction records (newest first):"]
        for txn in transactions:
            failure = f", Issue: {txn['failure_reason']}" if txn.get("failure_reason") else ""
            beneficiary = f", To: {txn['beneficiary_name']}" if txn.get("beneficiary_name") else ""
            lines.append(
                f"  - {txn.get('txn_date', '')} {txn.get('txn_type', '')} "
                f"{_fmt_amount(txn.get('amount'))} via {txn.get('channel', 'N/A')} "
                f"(ID: {txn.get('txn_id', '')}): "
                f"Status: {txn.get('status', 'Unknown')}"
                f"{beneficiary}{failure}"
            )
        return "\n".join(lines)

    return None
