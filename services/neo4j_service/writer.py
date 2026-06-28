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
    KYC, and loan Product links. IDs are deterministic from customer_id so
    repeated calls update records instead of duplicating them.
    """
    if client is None or not customer_id:
        return {"loans": 0, "claims": 0, "policies": 0, "kyc": 0, "product_links": 0}

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
            # Item 15: summary EMI schedule (this demo loan is Approved/disbursed).
            # Derived from amount 500000 @ 12.5% over 36 months (EMI formula).
            "emi_amount_inr": 16727,
            "outstanding_principal_inr": 416807,
            "next_emi_date": "2026-07-05",
            "foreclosure_amount_inr": 416807,
            "tenure_months": 36,
            "emis_paid": 7,
            # Item 17: Personal Loan is unsecured (no collateral); Approved -> fully disbursed.
            "sanctioned_amount_inr": 500000,
            "disbursed_amount_inr": 500000,
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
            # Item 17: Home Loan is secured (Property collateral); Under Review -> not disbursed.
            "collateral_type": "Property",
            "collateral_value_inr": 8000000,
            "ltv_percent": 75,
            "sanctioned_amount_inr": 6000000,
            "disbursed_amount_inr": 0,
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
                    l.phone = CASE WHEN $phone <> '' THEN $phone ELSE l.phone END,
                    l.emi_amount_inr = $emi_amount_inr,
                    l.outstanding_principal_inr = $outstanding_principal_inr,
                    l.next_emi_date = $next_emi_date,
                    l.foreclosure_amount_inr = $foreclosure_amount_inr,
                    l.tenure_months = $tenure_months,
                    l.emis_paid = $emis_paid,
                    l.dpd = $dpd,
                    l.overdue_amount_inr = $overdue_amount_inr,
                    l.penalty_inr = $penalty_inr,
                    l.arrears_bucket = $arrears_bucket,
                    l.collections_stage = $collections_stage,
                    l.collateral_type = $collateral_type,
                    l.collateral_value_inr = $collateral_value_inr,
                    l.ltv_percent = $ltv_percent,
                    l.sanctioned_amount_inr = $sanctioned_amount_inr,
                    l.disbursed_amount_inr = $disbursed_amount_inr
                WITH l
                MATCH (c:Customer {customer_id: $customer_id})
                MERGE (c)-[:HAS_LOAN]->(l)
                """,
                {
                    **loan, "customer_id": customer_id, "email": email or "", "phone": phone or "",
                    "emi_amount_inr": loan.get("emi_amount_inr", 0),
                    "outstanding_principal_inr": loan.get("outstanding_principal_inr", 0),
                    "next_emi_date": loan.get("next_emi_date", ""),
                    "foreclosure_amount_inr": loan.get("foreclosure_amount_inr", 0),
                    "tenure_months": loan.get("tenure_months", 0),
                    "emis_paid": loan.get("emis_paid", 0),
                    # Item 16: demo loans are current (no arrears).
                    "dpd": loan.get("dpd", 0),
                    "overdue_amount_inr": loan.get("overdue_amount_inr", 0),
                    "penalty_inr": loan.get("penalty_inr", 0),
                    "arrears_bucket": loan.get("arrears_bucket", "Current"),
                    "collections_stage": loan.get("collections_stage", "None"),
                    # Item 17: collateral (secured loans only) + disbursement.
                    "collateral_type": loan.get("collateral_type", ""),
                    "collateral_value_inr": loan.get("collateral_value_inr", 0),
                    "ltv_percent": loan.get("ltv_percent", 0),
                    "sanctioned_amount_inr": loan.get("sanctioned_amount_inr", 0),
                    "disbursed_amount_inr": loan.get("disbursed_amount_inr", 0),
                },
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
            # Synthetic per-customer policy fields, mirroring the Customer_Policy_data
            # loader so portal-seeded demo customers also get real policy_status data
            # (coverage/premium/etc.) instead of the old 3-field stub that returned nulls.
            # The two demo policy types (Health, Auto) are annual-renewal -> no maturity.
            policy_fields = {
                "Health": {"coverage_inr": 500000, "premium_inr": 12000},
                "Auto":   {"coverage_inr": 400000, "premium_inr": 9000},
            }.get(claim["policy_type"], {"coverage_inr": 500000, "premium_inr": 10000})
            client.write(
                """
                MERGE (p:Policy {policy_id: $policy_id})
                SET p.policy_type      = $policy_type,
                    p.customer_id      = $customer_id,
                    p.status           = 'Active',
                    p.coverage_inr     = $coverage_inr,
                    p.premium_inr      = $premium_inr,
                    p.premium_frequency = 'Annual',
                    p.premium_paid_to  = '2025-09-30',
                    p.next_premium_due = '2026-03-31',
                    p.maturity_date    = '',
                    p.premium_status   = 'Paid',
                    p.premiums_paid    = 3,
                    p.last_premium_date = '2025-09-30',
                    p.overdue_premium_inr = 0,
                    p.late_fee_inr     = 0,
                    p.grace_period_days = 30
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
                    "coverage_inr": policy_fields["coverage_inr"],
                    "premium_inr": policy_fields["premium_inr"],
                },
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
        }
    except Exception:
        logger.warning("neo4j_seed_synthetic_bfsi_records_failed", extra={"customer_id": customer_id}, exc_info=True)
        return {"loans": 0, "claims": 0, "policies": 0, "kyc": 0, "product_links": 0, "failed": True}


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
) -> None:
    """Write an :Interaction node in 'open' status the moment a message arrives.

    Called BEFORE the AI pipeline runs so the graph always has a record of every
    inbound message even if the pipeline fails partway through.
    """
    if client is None or not conversation_id or not customer_id:
        return
    try:
        client.write(
            """
            MERGE (i:Interaction {conversation_id: $conversation_id})
            SET i.channel    = $channel,
                i.message    = $message,
                i.status     = 'open',
                i.created_at = $timestamp
            WITH i
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:HAS_INTERACTION]->(i)
            """,
            {
                "conversation_id": conversation_id,
                "customer_id": customer_id,
                "channel": channel or "",
                "message": message_text or "",
                "timestamp": timestamp or "",
            },
        )
    except Exception:
        logger.warning(
            "neo4j_write_incoming_interaction_failed",
            extra={"conversation_id": conversation_id},
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
) -> None:
    """Update the :Interaction node with the AI resolution and create/update ResolutionMemory.

    Called AFTER the AI pipeline completes. Closes the open interaction and stores
    the answer as a reusable ResolutionMemory node keyed by (product_id, intent_type).
    """
    if client is None or not conversation_id:
        return
    try:
        from datetime import datetime, timezone
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        mem_id = "RESMEM-" + str(uuid.uuid4())[:8].upper()
        client.write(
            """
            MERGE (i:Interaction {conversation_id: $conversation_id})
            SET i.resolution           = $resolution,
                i.intent               = $intent,
                i.sentiment            = $sentiment,
                i.urgency              = $urgency,
                i.product_ref          = $product_id,
                i.resolution_embedding = $embedding,
                i.status               = 'closed',
                i.handled_by           = 'AI_GROQ',
                i.updated_at           = $now

            WITH i
            MERGE (rm:ResolutionMemory {product_id: $product_id, intent_type: $intent})
            ON CREATE SET
                rm.id                   = $mem_id,
                rm.query_pattern        = i.message,
                rm.resolution_text      = $resolution,
                rm.resolution_embedding = $embedding,
                rm.verified             = false,
                rm.times_reused         = 1,
                rm.created_at           = $now
            ON MATCH SET
                rm.resolution_text      = $resolution,
                rm.resolution_embedding = $embedding,
                rm.times_reused         = rm.times_reused + 1,
                rm.updated_at           = $now

            MERGE (i)-[:CREATED_MEMORY]->(rm)

            WITH i
            MATCH (a:Agent {agent_id: 'AI_GROQ'})
            MERGE (i)-[:HANDLED_BY]->(a)
            """,
            {
                "conversation_id": conversation_id,
                "resolution": resolution or "",
                "intent": intent or "",
                "sentiment": sentiment or "",
                "urgency": urgency or "",
                "product_id": product_id or "general",
                "embedding": embedding_str or "",
                "mem_id": mem_id,
                "now": now,
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
) -> None:
    """Create or update a :Ticket node and link it to the customer."""
    if client is None or not ticket_id or not customer_id:
        return
    try:
        client.write(
            """
            MERGE (t:Ticket {ticket_id: $ticket_id})
            SET t.intent   = $intent,
                t.priority = $priority,
                t.status   = $status
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
            },
        )
    except Exception:
        logger.warning(
            "neo4j_upsert_ticket_failed",
            extra={"ticket_id": ticket_id, "customer_id": customer_id},
            exc_info=True,
        )
