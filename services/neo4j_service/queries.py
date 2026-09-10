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
# The balance figure's qualifier lives IN ITS FIELD NAME, so the number cannot be emitted
# without it and it cannot attach to anything else.
#
# This used to be a NOTE line above the account rows, and it did two jobs: it stated facts
# ("this is an average, there is no live balance") AND it issued orders ("say so and point
# the customer to the mobile app", "Never describe this figure as their current balance").
# The orders are the problem. They sit inside a data block that goes to the model on every
# message, so the model obeyed them on questions that never touched the balance - an FD
# maturity question and a credit-card dues question both came back correct and then told the
# customer to check the app for their current balance. The prompt already carries the right
# rule ("Do NOT volunteer info about unrelated products"), but a directive next to the data
# outranks a general rule fifty lines earlier. See [[redact-dont-instruct-llm]]: removing the
# input works where instructing the model does not.
#
# The FACT is kept, because the balance answer depends on it: asked for a CURRENT balance,
# the model sees the only figure available is labelled as having no live/current counterpart,
# and the standing rule "answer ONLY using the retrieved context, do NOT invent facts" leaves
# it nothing else to say. Stating the absence is what makes that answer correct - not the
# instruction telling it what to write.
_BALANCE_LABEL = "Average monthly balance (this system has no live/current balance figure)"


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

    SERVICEABLE only, and stated as an INCLUSION list. This text is handed to the model as
    trusted context and can be quoted back to the customer, so a LOGGED ticket — an internal
    grouping id for a question that needed no human — must never appear here: that is the
    false "your request is already logged under tkt_x" claim Fix 119 removed.

    The previous form was `t.status IS NULL OR t.status <> 'closed'`, which would have
    admitted LOGGED silently. Note this also drops nodes with a NULL status, which the old
    clause deliberately included; a Ticket node is always written with a status by
    upsert_ticket_node, so a NULL means an incomplete write rather than an open case, and
    guessing "open" on incomplete data is what puts phantom cases in front of the model.
    """
    if client is None or not customer_id:
        return []
    try:
        return client.query(
            """
            MATCH (c:Customer {customer_id: $cid})-[:HAS_TICKET]->(t:Ticket)
            WHERE t.status IN ['open', 'in_progress']
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


# One query replaces the eight hand-written ones above, which each named the columns they
# wanted. That column list was a whitelist, and it was silently lossy in three ways:
#
#   1. FIELDS. Fathima asked "how many EMIs have I paid, and how many remain?" and was told
#      the system does not have her payment schedule. The Loan node holds emis_paid=53,
#      emis_pending=1, total_emis=54 - none of them in get_loan_status's RETURN clause.
#   2. NODE TYPES. Every customer has a :KYC node. No function fetched it, so "confirm my
#      KYC status" could not be answered from the customer's own record at all.
#   3. INTENTS. neo4j_answer gated on TRANSACTIONAL_INTENTS, so 9 of 16 intents received no
#      customer data whatever, and no intent routed to ChargePenalty - which is why a
#      Rs.1,284 late fee answered "I'm not seeing a transaction".
#
# Naming nothing is what fixes all three at once: a property added to a node, or a new node
# type in the seed, appears without anyone remembering to edit a query.
#
# Measured before choosing this over a relevance ranker (2026-09-04, real records, 14 real
# questions from the sample workbook):
#
#   today's hardcoded pair of filters   31-36 fields   ~256 tokens   fails EMI/KYC/charges
#   rank per record, 15 each           108-135        ~999          14/14
#   rank across all records, top 50     ~50           ~344          14/14
#   THIS - everything                  139-165       ~1000          14/14
#
# Per-record ranking cost the same as sending everything and could still drop a needed
# field, so it bought nothing. Customer-level ranking was a third of the cost - but a
# dropped field is INVISIBLE to the model: it cannot distinguish "this customer has no
# annual fee" from "the annual fee did not score high enough", so system.md's "if you do
# not have the data, say so" cannot fire and a confidently wrong total becomes possible.
# That trade is wrong in a financial context when the quota that actually binds is
# REQUESTS (1000/day), not tokens - the extra ~750 tokens sit inside a ~10,100 token
# message and change the request count not at all.
_ALL_RECORDS_CYPHER = """
MATCH (c:Customer {customer_id: $cid})-[r]->(n)
WHERE NOT n:Interaction AND NOT n:Ticket
OPTIONAL MATCH (p:Policy)-[:HAS_CLAIM]->(n)
RETURN labels(n)[0] AS label, properties(n) AS props,
       p.policy_type AS parent_policy_type
"""

# Every KB chunk, each marked with whether this customer holds the subject it explains.
#
# NOT a retrieval query - there is no scoring, no top-k and no similarity here. The KB is
# 14 chunks (~1,124 tokens) inside a ~10,100 token message, against a quota bound by
# REQUESTS (1000/day), so selecting a subset buys nothing and can drop the one chunk that
# answers the question. The same reasoning that made _ALL_RECORDS_CYPHER return every
# field applies to the KB: a chunk that was filtered out is invisible to the model, which
# cannot tell "the bank has no guidance on this" from "the guidance did not rank".
#
# `is_hers` comes from the graph, not from the text: her holdings walk to a Concept, and a
# chunk explaining that same Concept is about something she actually has. That mark is what
# lets the model prefer her situation over general guidance when both could answer.
#
# Chunks whose Concept nobody sells (SIP, ELSS, Demat) arrive like any other - they are
# Concepts with no Product child, which is a fact about the catalogue, not a gap.
_GUIDANCE_CYPHER = """
OPTIONAL MATCH (c:Customer {customer_id: $cid})-[]->(h)-[:INSTANCE_OF]->(held:Concept)
WITH collect(DISTINCT held.name) AS held_names
MATCH (k:KBChunk {doc_type: 'knowledge_base'})-[:EXPLAINS]->(con:Concept)
RETURN k.text AS text, con.name AS concept,
       (con.name IN held_names) AS is_hers
ORDER BY is_hers DESC, con.name
"""

# Rows, not fields. Eight is the cap neo4j_answer already applied to transactions: a dispute
# is nearly always about a recent debit, and 72 rows would crowd out the customer's actual
# question. This is the one bound that survives, and it limits HOW MANY RECORDS, never
# which fields within one.
_ROW_CAPS = {"Transaction": 8}

# The graph label -> the key the context dict has always used. Callers of
# get_customer_context_for_customer (the opportunity engine, next-best-action, the
# agent-assist route, the ticket manager) read these keys, so they must not move.
_LABEL_TO_KEY = {
    "Loan": "loans",
    "Claim": "claims",
    "Policy": "policies",
    "CreditCard": "credit_cards",
    "Account": "accounts",
    "FixedDeposit": "fixed_deposits",
    "Transaction": "transactions",
    "ChargePenalty": "charges",
    "KYC": "kyc",
}

# Transactions carry no date-ordered guarantee from the walk above, so sort what we cap.
_ROW_SORT_KEY = {"Transaction": "txn_date"}


def get_guidance(client, customer_id: str) -> list[dict]:
    """Every KB chunk, each flagged with whether it explains something this customer holds.

    Returns [] on any failure. The caller then has the customer's records and no
    guidance, which is exactly the behaviour before the Concept layer existed - the
    KB simply does not reach the prompt, and the reply is built from records alone.
    """
    if client is None:
        return []
    try:
        rows = client.query(_GUIDANCE_CYPHER, {"cid": customer_id or ""})
    except Exception:
        return []
    return [
        {
            "text": row.get("text") or "",
            "concept": row.get("concept") or "",
            "is_hers": bool(row.get("is_hers")),
        }
        for row in rows or []
        if row.get("text")
    ]


def get_all_customer_records(client, customer_id: str) -> dict[str, list[dict]]:
    """Every record this customer is connected to, every field, grouped by context key.

    Returns {} on any failure rather than raising: the caller falls back to the knowledge
    base, which is the same behaviour the eight individual getters had.
    """
    if client is None or not customer_id:
        return {}
    try:
        rows = client.query(_ALL_RECORDS_CYPHER, {"cid": customer_id})
    except Exception:
        return {}

    grouped: dict[str, list[dict]] = {}
    for row in rows or []:
        label = row.get("label")
        props = dict(row.get("props") or {})
        if not label or not props:
            continue
        # get_claim_status joined the parent Policy for its type, and the reply text uses it
        # ("Auto / Total Loss"), so the join is preserved rather than dropped with the
        # column list.
        if label == "Claim" and row.get("parent_policy_type"):
            props.setdefault("policy_type", row["parent_policy_type"])
        grouped.setdefault(_LABEL_TO_KEY.get(label, label.lower()), []).append(props)

    for label, cap in _ROW_CAPS.items():
        key = _LABEL_TO_KEY.get(label, label.lower())
        records = grouped.get(key)
        if records and len(records) > cap:
            sort_field = _ROW_SORT_KEY.get(label)
            if sort_field:
                records.sort(key=lambda item: str(item.get(sort_field) or ""), reverse=True)
            grouped[key] = records[:cap]
    return grouped


def get_customer_context_for_customer(client, customer: dict | None) -> dict:
    """Return a rich context dict for an already resolved Neo4j customer.

    The KEYS are unchanged - five other surfaces read them - but each record now carries
    every field it has rather than the handful its old query named. Extra keys are additive,
    so nothing downstream breaks; `charges` and `kyc` are new and were previously
    unreachable from this path entirely.
    """
    if not customer:
        return {}
    cid = customer["customer_id"]
    records = get_all_customer_records(client, cid)
    return {
        "customer_id": cid,
        "name": customer.get("name"),
        "email": customer.get("email"),
        "phone": customer.get("phone"),
        "city": customer.get("city"),
        "segment": customer.get("segment"),
        "loans": records.get("loans", []),
        "claims": records.get("claims", []),
        "policies": records.get("policies", []),
        "credit_cards": records.get("credit_cards", []),
        "accounts": records.get("accounts", []),
        "fixed_deposits": records.get("fixed_deposits", []),
        "transactions": records.get("transactions", []),
        "charges": records.get("charges", []),
        "kyc": records.get("kyc", []),
        "open_cases": get_open_cases(client, cid),
    }


def _fmt_amount(value) -> str:
    """Safely format a currency amount that may be stored as int, float, or string."""
    try:
        return f"Rs.{int(float(str(value).replace(',', ''))):,}"
    except (ValueError, TypeError):
        return str(value) if value else "N/A"


def neo4j_answer(client, intent: str | None, customer_id: str) -> str | None:
    """The customer's own records, rendered for the prompt. None when they have none.

    This function used to branch on the intent label: seven `if intent == "..."` arms, each
    building a hand-written line from a handful of fields, behind a TRANSACTIONAL_INTENTS
    gate that returned None for the other nine intents. Three separate losses came out of
    that shape - fields the arm did not name (emis_paid on a question asking for exactly
    that), node types no arm covered (:KYC), and whole intents the gate excluded (no arm
    ever reached ChargePenalty, so a Rs.1,284 late fee answered "I'm not seeing a
    transaction").

    It now renders every record the customer holds. `intent` is accepted and ignored, kept
    only so the call sites need not change; the label no longer decides what a customer is
    allowed to be told about their own account.
    """
    if client is None or not customer_id:
        return None
    records = get_all_customer_records(client, customer_id)
    if not records:
        return None

    from services.rag_service.groq_generator import _RECORD_SECTIONS, _format_record

    lines: list[str] = []
    for key, heading in _RECORD_SECTIONS:
        rows = records.get(key) or []
        if not rows:
            continue
        lines.append(f"{heading}:")
        for row in rows:
            lines.append("  - " + _format_record(row))

    # The KB is deliberately NOT appended here. The caller emits the same chunks as
    # entries in `contexts` (orchestration_agents.py), and every context's text is
    # concatenated into the prompt by GroqGenerator.generate_answer - so returning
    # them here too would send all 14 chunks twice, ~1,124 tokens of exact duplicate
    # per message. contexts is the right home: it carries the provenance metadata
    # that citations, retrieval evidence and the agent console all read, which a
    # block of text inside this string cannot.
    return "\n".join(lines) if lines else None
