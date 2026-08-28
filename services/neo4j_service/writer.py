"""Real-time Neo4j writer for runtime customer interaction data.

All functions use MERGE so they are safe to call repeatedly with the same IDs —
existing nodes are updated, new nodes are created. Every function is a no-op when
``client`` is None so callers don't need to guard against a disabled graph.
"""

import logging

logger = logging.getLogger(__name__)


def seed_synthetic_bfsi_records(
    client,
    customer_id: str,
    registration_date: str,
    email: str = "",
    phone: str = "",
) -> dict:
    """Create demo BFSI graph records for a newly signed-up portal customer.

    The generated nodes follow the same labels, properties, and relationships
    used by ``data/bfsi.xlsx`` loader rows: Customer has Loan, Claim, Policy,
    Account, CreditCard, FixedDeposit, and KYC. IDs are deterministic from
    customer_id so repeated calls update records instead of duplicating them.
    """
    if client is None or not customer_id:
        return {"loans": 0, "claims": 0, "policies": 0, "kyc": 0, "product_links": 0,
                "accounts": 0, "credit_cards": 0, "fixed_deposits": 0}

    suffix = "".join(ch for ch in customer_id if ch.isdigit())[-6:] or "000000"
    last_updated = registration_date or ""
    loans = [
        {
            "loan_id": f"LN{suffix}01",
            "loan_type": "Personal Loan",
            "application_date": registration_date,
            "status": "Approved",
            "last_updated": last_updated,
            "amount_inr": 500000,
            "interest_rate": "12.5",
            "next_step": "Disbursement pending",
        },
        {
            "loan_id": f"LN{suffix}02",
            "loan_type": "Home Loan",
            "application_date": registration_date,
            "status": "Under Review",
            "last_updated": last_updated,
            "amount_inr": 6000000,
            "interest_rate": "8.2",
            "next_step": "Property valuation",
        },
    ]
    claims = [
        {
            "claim_id": f"CLM{suffix}01",
            "policy_type": "Health",
            "claim_type": "Hospitalization",
            "status": "Approved",
            "last_updated": last_updated,
            "amount_claimed": 50000,
            "amount_approved": 45000,
            "reason": "Documents verified",
        },
        {
            "claim_id": f"CLM{suffix}02",
            "policy_type": "Auto",
            "claim_type": "Minor Damage",
            "status": "Under Review",
            "last_updated": last_updated,
            "amount_claimed": 15000,
            "amount_approved": "N/A",
            "reason": "Awaiting repair estimate",
        },
    ]

    try:
        for loan in loans:
            client.write(
                """
                MERGE (l:Loan {loan_id: $loan_id})
                SET l.loan_type = $loan_type,
                    l.application_date = $application_date,
                    l.status = $status,
                    l.last_updated = $last_updated,
                    l.amount_inr = $amount_inr,
                    l.interest_rate = $interest_rate,
                    l.next_step = $next_step,
                    l.email = CASE WHEN $email <> '' THEN $email ELSE l.email END,
                    l.phone = CASE WHEN $phone <> '' THEN $phone ELSE l.phone END
                WITH l
                MATCH (c:Customer {customer_id: $customer_id})
                MERGE (c)-[:HAS_LOAN]->(l)
                """,
                {**loan, "customer_id": customer_id, "email": email or "", "phone": phone or ""},
            )
            client.write(
                """
                MATCH (l:Loan {loan_id: $loan_id})
                MATCH (p:Product)
                WHERE p.product_type = $loan_type
                   OR p.name CONTAINS $loan_type
                   OR p.category = $loan_type
                MERGE (l)-[:PRODUCT_IS]->(p)
                """,
                {"loan_id": loan["loan_id"], "loan_type": loan["loan_type"]},
            )

        policy_types = set()
        for claim in claims:
            policy_types.add(claim["policy_type"])
            client.write(
                """
                MERGE (cl:Claim {claim_id: $claim_id})
                SET cl.policy_type = $policy_type,
                    cl.claim_type = $claim_type,
                    cl.status = $status,
                    cl.last_updated = $last_updated,
                    cl.amount_claimed_inr = $amount_claimed,
                    cl.amount_approved_inr = $amount_approved,
                    cl.reason = $reason,
                    cl.email = CASE WHEN $email <> '' THEN $email ELSE cl.email END,
                    cl.phone = CASE WHEN $phone <> '' THEN $phone ELSE cl.phone END
                WITH cl
                MATCH (c:Customer {customer_id: $customer_id})
                MERGE (c)-[:HAS_CLAIM]->(cl)
                """,
                {**claim, "customer_id": customer_id, "email": email or "", "phone": phone or ""},
            )

            policy_id = f"{customer_id}_{claim['policy_type'].replace(' ', '_').upper()}"
            client.write(
                """
                MERGE (p:Policy {policy_id: $policy_id})
                SET p.policy_type = $policy_type,
                    p.customer_id = $customer_id,
                    p.status = 'Active'
                WITH p
                MATCH (c:Customer {customer_id: $customer_id})
                MERGE (c)-[:HAS_POLICY]->(p)
                WITH p
                MATCH (cl:Claim {claim_id: $claim_id})
                MERGE (p)-[:HAS_CLAIM]->(cl)
                """,
                {
                    "policy_id": policy_id,
                    "policy_type": claim["policy_type"],
                    "customer_id": customer_id,
                    "claim_id": claim["claim_id"],
                },
            )

        account_number = f"4090{suffix}00"
        client.write(
            """
            MERGE (a:Account {account_number: $account_number})
            SET a.account_category = 'Deposit',
                a.account_type = 'SA',
                a.account_sub_type = 'Regular',
                a.opening_date = $registration_date,
                a.status = 'Active',
                a.avg_monthly_balance = 5000,
                a.min_balance_required = 3000,
                a.currency = 'INR'
            WITH a
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:HAS_ACCOUNT]->(a)
            """,
            {"account_number": account_number, "customer_id": customer_id, "registration_date": registration_date or ""},
        )
        client.write(
            """
            MERGE (cc:CreditCard {card_id: $card_id})
            SET cc.account_number = $account_number,
                cc.credit_limit = 200000,
                cc.card_network = 'Visa',
                cc.card_variant = 'Classic',
                cc.balance_due = 0,
                cc.min_amount_due = 0,
                cc.total_amount_due = 0,
                cc.dpd = 0,
                cc.interest_rate = 38.0,
                cc.penalty_details = 'None',
                cc.reward_points_balance = 0,
                cc.chargeback_flag = false,
                cc.fraud_flag = false
            WITH cc
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:HAS_CREDIT_CARD]->(cc)
            """,
            {"card_id": f"CC{suffix}01", "account_number": account_number, "customer_id": customer_id},
        )
        client.write(
            """
            MERGE (fd:FixedDeposit {fd_id: $fd_id})
            SET fd.account_number = $account_number,
                fd.principal_amount = 100000,
                fd.interest_rate = 7.0,
                fd.tenure_months = 12,
                fd.booking_date = $registration_date,
                fd.status = 'Active'
            WITH fd
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:HAS_FD]->(fd)
            """,
            {"fd_id": f"FD{suffix}01", "account_number": account_number, "customer_id": customer_id, "registration_date": registration_date or ""},
        )

        client.write(
            """
            MERGE (k:KYC {customer_id: $customer_id})
            SET k.kyc_status = 'Pending',
                k.registered_at = $registered_at
            WITH k
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:KYC_VERIFIED_BY]->(k)
            """,
            {"customer_id": customer_id, "registered_at": registration_date or ""},
        )
        return {
            "loans": len(loans),
            "claims": len(claims),
            "policies": len(policy_types),
            "kyc": 1,
            "product_links": len(loans),
            "accounts": 1,
            "credit_cards": 1,
            "fixed_deposits": 1,
        }
    except Exception:
        logger.warning("neo4j_seed_synthetic_bfsi_records_failed", extra={"customer_id": customer_id}, exc_info=True)
        return {"loans": 0, "claims": 0, "policies": 0, "kyc": 0, "product_links": 0,
                "accounts": 0, "credit_cards": 0, "fixed_deposits": 0, "failed": True}


def upsert_customer(
    client,
    customer_id: str,
    phone: str,
    name: str,
    channel: str = "",
    email: str = "",
    secondary_email: str = "",
    city: str = "",
    country: str = "",
    registration_date: str = "",
    last_activity_date: str = "",
) -> None:
    """Create or update a :Customer node from a runtime inbound message.

    If the customer already exists (loaded from bfsi.xlsx), only the runtime
    fields (phone, display_name, channel) are SET — BFSI fields like loans/claims
    are untouched.
    """
    if client is None or not customer_id:
        return
    try:
        client.write(
            """
            MERGE (c:Customer {customer_id: $customer_id})
            SET c.phone        = CASE WHEN $phone <> '' THEN $phone ELSE c.phone END,
                c.email        = CASE WHEN $email <> '' THEN $email ELSE c.email END,
                c.secondary_email = CASE WHEN $secondary_email <> '' THEN $secondary_email ELSE c.secondary_email END,
                c.city         = CASE WHEN $city <> '' THEN $city ELSE c.city END,
                c.country      = CASE WHEN $country <> '' THEN $country ELSE c.country END,
                c.registration_date = CASE WHEN $registration_date <> '' THEN $registration_date ELSE c.registration_date END,
                c.last_activity_date = CASE WHEN $last_activity_date <> '' THEN $last_activity_date ELSE c.last_activity_date END,
                c.display_name = CASE WHEN $name  <> '' THEN $name  ELSE c.display_name END,
                c.channel      = $channel
            """,
            {
                "customer_id": customer_id,
                "phone": phone or "",
                "email": email or "",
                "secondary_email": secondary_email or "",
                "city": city or "",
                "country": country or "",
                "registration_date": registration_date or "",
                "last_activity_date": last_activity_date or "",
                "name": name or "",
                "channel": channel,
            },
        )
    except Exception:
        logger.warning("neo4j_upsert_customer_failed", extra={"customer_id": customer_id}, exc_info=True)


def upsert_interaction(
    client,
    customer_id: str,
    conversation_id: str,
    intent: str,
    urgency: str,
    channel: str,
    timestamp: str,
) -> None:
    """Create or update an :Interaction node and link it to the customer.

    Each conversation_id maps to exactly one Interaction node. Repeated calls
    (e.g., multiple turns in the same conversation) update the existing node.
    """
    if client is None or not customer_id or not conversation_id:
        return
    try:
        client.write(
            """
            MERGE (i:Interaction {conversation_id: $conversation_id})
            SET i.intent    = $intent,
                i.urgency   = $urgency,
                i.channel   = $channel,
                i.timestamp = $timestamp
            WITH i
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:HAS_INTERACTION]->(i)
            """,
            {
                "conversation_id": conversation_id,
                "customer_id": customer_id,
                "intent": intent or "",
                "urgency": urgency or "",
                "channel": channel or "",
                "timestamp": timestamp or "",
            },
        )
    except Exception:
        logger.warning(
            "neo4j_upsert_interaction_failed",
            extra={"customer_id": customer_id, "conversation_id": conversation_id},
            exc_info=True,
        )


def write_incoming_interaction(
    client,
    conversation_id: str,
    customer_id: str,
    channel: str,
    message_text: str,
    timestamp: str,
    turn_id: str | None = None,
) -> None:
    """Write an :Interaction node in 'open' status the moment a message arrives.

    Called BEFORE the AI pipeline runs so the graph always has a record of every
    inbound message even if the pipeline fails partway through.

    Keyed on turn_id when one is supplied, so each customer MESSAGE is its own node.
    It used to MERGE on conversation_id alone, which meant every new message
    OVERWROTE the previous one: a 12-turn conversation left a single node holding
    only the last sentence. The graph could therefore show what a customer holds
    but never what they had been dealing with — the conversation history existed
    only in SQLite. The conversation_id stays on the node so a whole thread can
    still be fetched with one match.

    turn_id is optional so existing callers (and the seed loader, whose rows are
    genuinely one-per-conversation) keep the previous behaviour unchanged.
    """
    if client is None or not conversation_id or not customer_id:
        return
    try:
        key_clause = (
            "MERGE (i:Interaction {turn_id: $turn_id})"
            if turn_id else
            "MERGE (i:Interaction {conversation_id: $conversation_id})"
        )
        client.write(
            f"""
            {key_clause}
            SET i.conversation_id = $conversation_id,
                i.channel         = $channel,
                i.message         = $message,
                i.status          = 'open',
                i.created_at      = $timestamp
            WITH i
            MATCH (c:Customer {{customer_id: $customer_id}})
            MERGE (c)-[:HAS_INTERACTION]->(i)
            """,
            {
                "conversation_id": conversation_id,
                "customer_id": customer_id,
                "channel": channel or "",
                "message": message_text or "",
                "timestamp": timestamp or "",
                "turn_id": turn_id or "",
            },
        )
    except Exception:
        logger.warning(
            "neo4j_write_incoming_interaction_failed",
            extra={"conversation_id": conversation_id},
            exc_info=True,
        )


def link_interaction_to_ticket(client, turn_id: str, ticket_id: str) -> None:
    """Attach a message to the ticket it belongs to: (:Ticket)-[:HAS_MESSAGE]->(:Interaction).

    Without this edge the graph holds tickets and messages as disconnected islands —
    it can answer "what does this customer hold?" but not "what has been said about
    this case?", which is the half of the story the knowledge graph exists to show.
    Both nodes must already exist; MATCH (not MERGE) so a missing node writes nothing
    rather than creating an empty placeholder.
    """
    if client is None or not turn_id or not ticket_id:
        return
    try:
        client.write(
            """
            MATCH (t:Ticket {ticket_id: $ticket_id})
            MATCH (i:Interaction {turn_id: $turn_id})
            MERGE (t)-[:HAS_MESSAGE]->(i)
            """,
            {"ticket_id": ticket_id, "turn_id": turn_id},
        )
    except Exception:
        logger.warning(
            "neo4j_link_interaction_to_ticket_failed",
            extra={"turn_id": turn_id, "ticket_id": ticket_id},
            exc_info=True,
        )


def update_interaction_resolution(
    client,
    conversation_id: str,
    customer_id: str,
    resolution: str,
    intent: str,
    sentiment: str,
    product_id: str,
    embedding_str: str,
    urgency: str,
    turn_id: str | None = None,
    memory_key: str | None = None,
) -> None:
    """Update the :Interaction node with the AI resolution and create/update ResolutionMemory.

    Called AFTER the AI pipeline completes. Closes the open interaction and stores
    the answer as a reusable ResolutionMemory node keyed by (product_id, intent_type).

    Must key on the SAME field write_incoming_interaction used, or it MERGEs a second,
    competing node: the per-message node stays 'open' forever while a conversation-keyed
    duplicate holds the resolution.
    """
    if client is None or not conversation_id:
        return
    try:
        from datetime import datetime, timezone
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        mem_id = "RESMEM-" + str(uuid.uuid4())[:8].upper()
        key_clause = (
            "MERGE (i:Interaction {turn_id: $turn_id})"
            if turn_id else
            "MERGE (i:Interaction {conversation_id: $conversation_id})"
        )
        client.write(
            f"""
            {key_clause}
            SET i.conversation_id      = $conversation_id,
                i.resolution           = $resolution,
                i.intent               = $intent,
                i.sentiment            = $sentiment,
                i.urgency              = $urgency,
                i.product_ref          = $product_id,
                i.resolution_embedding = $embedding,
                i.status               = 'closed',
                i.handled_by           = 'AI_GROQ',
                i.updated_at           = $now

            WITH i
            MERGE (rm:ResolutionMemory {{memory_key: $memory_key}})
            ON CREATE SET
                rm.id                   = $mem_id,
                rm.intent_type          = $intent,
                rm.product_id           = $product_id,
                rm.query_pattern        = i.message,
                rm.resolution_text      = $resolution,
                rm.resolution_embedding = $embedding,
                rm.verified             = false,
                rm.times_reused         = 0,
                rm.created_at           = $now
            ON MATCH SET
                rm.intent_type          = $intent,
                rm.updated_at           = $now,
                // A human-verified answer IS the reward signal: the next unverified
                // generation must never overwrite it. Only refresh while unverified.
                rm.resolution_text      = CASE WHEN coalesce(rm.verified, false)
                                               THEN rm.resolution_text ELSE $resolution END,
                rm.resolution_embedding = CASE WHEN coalesce(rm.verified, false)
                                               THEN rm.resolution_embedding ELSE $embedding END

            MERGE (i)-[:CREATED_MEMORY]->(rm)

            WITH i
            MATCH (a:Agent {{agent_id: 'AI_GROQ'}})
            MERGE (i)-[:HANDLED_BY]->(a)
            """,
            {
                "conversation_id": conversation_id,
                "resolution": resolution or "",
                "intent": intent or "",
                "sentiment": sentiment or "",
                "urgency": urgency or "",
                "product_id": product_id or "general",
                "memory_key": memory_key or f"{intent or 'unknown'}:general",
                "embedding": embedding_str or "",
                "mem_id": mem_id,
                "now": now,
                "turn_id": turn_id or "",
            },
        )
    except Exception:
        logger.warning(
            "neo4j_update_interaction_resolution_failed",
            extra={"conversation_id": conversation_id},
            exc_info=True,
        )


def upsert_ticket_node(
    client,
    ticket_id: str,
    customer_id: str,
    intent: str,
    priority: str,
    status: str,
    ticket_scope: str | None = None,
    title: str | None = None,
) -> None:
    """Create or update a :Ticket node and link it to the customer.

    ticket_scope is the sub-matter label ("transaction_dispute:imps") that SQLite uses
    to decide whether a later message continues this ticket. Storing it on the node
    means the graph can show WHICH specific matter a ticket is about, and that a vague
    opener was later refined — otherwise every dispute node looks identical.
    """
    if client is None or not ticket_id or not customer_id:
        return
    try:
        client.write(
            """
            MERGE (t:Ticket {ticket_id: $ticket_id})
            SET t.intent   = $intent,
                t.priority = $priority,
                t.status   = $status,
                t.scope    = $ticket_scope,
                t.title    = $title
            WITH t
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:HAS_TICKET]->(t)
            """,
            {
                "ticket_id": ticket_id,
                "customer_id": customer_id,
                "intent": intent or "",
                "priority": priority or "",
                "status": status or "",
                "ticket_scope": ticket_scope or "",
                "title": title or "",
            },
        )
    except Exception:
        logger.warning(
            "neo4j_upsert_ticket_failed",
            extra={"ticket_id": ticket_id, "customer_id": customer_id},
            exc_info=True,
        )
