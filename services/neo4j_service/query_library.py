"""BFSI Neo4j query library — customer 360, resolution memory, and analytics.

All functions accept a Neo4jClient (or None) and return plain Python dicts/lists.
Every function is a safe no-op when client is None.
"""

import logging

logger = logging.getLogger(__name__)


# ── Customer 360 ─────────────────────────────────────────────────────────────

def get_customer_360(client, phone_or_email: str) -> dict:
    """Full customer context: profile, loans, claims, policies, open interactions, KYC.

    Richer than get_customer_context() — includes policies and interaction history.
    """
    if client is None or not phone_or_email:
        return {}
    try:
        rows = client.query(
            """
            MATCH (c:Customer)
            WHERE c.phone = $id OR c.email = $id OR c.secondary_email = $id
            OPTIONAL MATCH (c)-[:HAS_LOAN]->(l:Loan)
            OPTIONAL MATCH (c)-[:HAS_CLAIM]->(cl:Claim)
            OPTIONAL MATCH (c)-[:HAS_POLICY]->(p:Policy)
            OPTIONAL MATCH (c)-[:HAS_INTERACTION]->(i:Interaction) WHERE i.status = 'open'
            OPTIONAL MATCH (c)-[:KYC_VERIFIED_BY]->(k:KYC)
            RETURN
                c.customer_id     AS customer_id,
                c.email           AS email,
                c.phone           AS phone,
                c.city            AS city,
                c.country         AS country,
                k.kyc_status      AS kyc_status,
                collect(DISTINCT {
                    loan_id:      l.loan_id,
                    loan_type:    l.loan_type,
                    status:       l.status,
                    amount_inr:   l.amount_inr,
                    interest_rate: l.interest_rate,
                    next_step:    l.next_step,
                    last_updated: l.last_updated
                }) AS loans,
                collect(DISTINCT {
                    claim_id:     cl.claim_id,
                    policy_type:  cl.policy_type,
                    claim_type:   cl.claim_type,
                    status:       cl.status,
                    amount_claimed: cl.amount_claimed_inr,
                    amount_approved: cl.amount_approved_inr,
                    reason:       cl.reason
                }) AS claims,
                collect(DISTINCT {
                    policy_id:    p.policy_id,
                    policy_type:  p.policy_type,
                    status:       p.status
                }) AS policies,
                collect(DISTINCT {
                    conversation_id: i.conversation_id,
                    channel:         i.channel,
                    message:         i.message,
                    status:          i.status,
                    created_at:      i.created_at
                }) AS open_interactions
            LIMIT 1
            """,
            {"id": phone_or_email},
        )
        if not rows:
            return {}
        row = rows[0]
        # Filter out null-valued collect results (Neo4j includes {key: null} dicts)
        return {
            "customer_id": row.get("customer_id"),
            "email": row.get("email"),
            "phone": row.get("phone"),
            "city": row.get("city"),
            "country": row.get("country"),
            "kyc_status": row.get("kyc_status", "Unknown"),
            "loans": [l for l in (row.get("loans") or []) if l.get("loan_id")],
            "claims": [c for c in (row.get("claims") or []) if c.get("claim_id")],
            "policies": [p for p in (row.get("policies") or []) if p.get("policy_id")],
            "open_interactions": [i for i in (row.get("open_interactions") or []) if i.get("conversation_id")],
        }
    except Exception:
        logger.warning("neo4j_get_customer_360_failed", extra={"id": phone_or_email}, exc_info=True)
        return {}


# ── Resolution Memory ─────────────────────────────────────────────────────────

def search_resolution_memory(client, product_id: str, intent_type: str) -> dict | None:
    """Return a cached resolution for a (product_id, intent_type) combination.

    Returns None if not found or if the memory is not yet verified.
    Only returns verified answers to prevent stale/wrong cached responses.
    """
    if client is None or not product_id or not intent_type:
        return None
    try:
        rows = client.query(
            """
            MATCH (rm:ResolutionMemory {product_id: $product_id, intent_type: $intent})
            RETURN rm.resolution_text AS resolution,
                   rm.times_reused   AS times_reused,
                   rm.verified       AS verified,
                   rm.query_pattern  AS query_pattern
            ORDER BY rm.times_reused DESC
            LIMIT 1
            """,
            {"product_id": product_id, "intent": intent_type},
        )
        return rows[0] if rows else None
    except Exception:
        logger.warning("neo4j_search_resolution_memory_failed", exc_info=True)
        return None


def verify_resolution_memory(client, product_id: str, intent_type: str) -> None:
    """Mark a ResolutionMemory node as agent-verified (safe to serve without RAG)."""
    if client is None:
        return
    try:
        client.write(
            """
            MATCH (rm:ResolutionMemory {product_id: $product_id, intent_type: $intent})
            SET rm.verified = true, rm.verified_at = $now
            """,
            {
                "product_id": product_id,
                "intent": intent_type,
                "now": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            },
        )
    except Exception:
        logger.warning("neo4j_verify_resolution_memory_failed", exc_info=True)


# ── Open Issues ───────────────────────────────────────────────────────────────

def find_open_issues(client, customer_id: str) -> dict:
    """Get all pending claims, active loans, and open interactions for a customer."""
    if client is None or not customer_id:
        return {"pending_claims": [], "active_loans": [], "open_interactions": []}
    try:
        rows = client.query(
            """
            MATCH (c:Customer {customer_id: $customer_id})
            OPTIONAL MATCH (c)-[:HAS_CLAIM]->(cl:Claim)
            WHERE cl.status IN ['Submitted', 'Under Review', 'Processing']
            OPTIONAL MATCH (c)-[:HAS_LOAN]->(l:Loan)
            WHERE l.status IN ['Processing', 'Under Review', 'Approved']
            OPTIONAL MATCH (c)-[:HAS_INTERACTION]->(i:Interaction)
            WHERE i.status = 'open'
            RETURN
                collect(DISTINCT {claim_id: cl.claim_id, policy_type: cl.policy_type,
                                   status: cl.status, reason: cl.reason}) AS pending_claims,
                collect(DISTINCT {loan_id: l.loan_id, loan_type: l.loan_type,
                                   status: l.status, next_step: l.next_step}) AS active_loans,
                collect(DISTINCT {conversation_id: i.conversation_id, channel: i.channel,
                                   message: i.message, created_at: i.created_at}) AS open_interactions
            """,
            {"customer_id": customer_id},
        )
        if not rows:
            return {"pending_claims": [], "active_loans": [], "open_interactions": []}
        row = rows[0]
        return {
            "pending_claims": [c for c in (row.get("pending_claims") or []) if c.get("claim_id")],
            "active_loans": [l for l in (row.get("active_loans") or []) if l.get("loan_id")],
            "open_interactions": [i for i in (row.get("open_interactions") or []) if i.get("conversation_id")],
        }
    except Exception:
        logger.warning("neo4j_find_open_issues_failed", extra={"customer_id": customer_id}, exc_info=True)
        return {"pending_claims": [], "active_loans": [], "open_interactions": []}


# ── Cross-sell Analytics ──────────────────────────────────────────────────────

def get_cross_sell_candidates(client, limit: int = 50) -> list[dict]:
    """Return customers who have loans but no life or term insurance policy.

    These are prime candidates for term plan cross-sell campaigns.
    """
    if client is None:
        return []
    try:
        return client.query(
            """
            MATCH (c:Customer)-[:HAS_LOAN]->(l:Loan)
            WHERE NOT (c)-[:HAS_POLICY]->(:Policy {policy_type: 'Term Insurance'})
              AND NOT (c)-[:HAS_POLICY]->(:Policy {policy_type: 'Life'})
              AND NOT (c)-[:HAS_POLICY]->(:Policy {policy_type: 'Life Insurance'})
            WITH c, collect(l.loan_type) AS loan_types
            RETURN c.customer_id AS customer_id,
                   c.phone       AS phone,
                   c.email       AS email,
                   c.city        AS city,
                   loan_types
            LIMIT $limit
            """,
            {"limit": limit},
        )
    except Exception:
        logger.warning("neo4j_get_cross_sell_candidates_failed", exc_info=True)
        return []


# ── Vector Indexes ────────────────────────────────────────────────────────────

def create_vector_indexes(client, dimension: int = 384) -> dict:
    """Create vector indexes on ResolutionMemory and Interaction nodes.

    Requires Neo4j 5.11+. Gracefully skips if the version doesn't support it.
    Returns a status dict with results for each index.
    """
    if client is None:
        return {"status": "skipped", "reason": "no client"}

    results = {}
    indexes = [
        ("resolution_memory_idx", "ResolutionMemory", "resolution_embedding"),
        ("interaction_resolution_idx", "Interaction", "resolution_embedding"),
    ]
    for idx_name, label, prop in indexes:
        try:
            client.write(
                f"""
                CREATE VECTOR INDEX {idx_name} IF NOT EXISTS
                FOR (n:{label}) ON (n.{prop})
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {dimension},
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
                """
            )
            results[idx_name] = "created"
        except Exception as exc:
            err = str(exc)
            if "already exists" in err.lower() or "equivalent index already exists" in err.lower():
                results[idx_name] = "already_exists"
            else:
                results[idx_name] = f"failed: {err[:120]}"
    return {"status": "done", "indexes": results}
