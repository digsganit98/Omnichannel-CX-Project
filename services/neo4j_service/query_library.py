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
            OPTIONAL MATCH (c)-[:HAS_ACCOUNT]->(a:Account)
            OPTIONAL MATCH (c)-[:HAS_CREDIT_CARD]->(cc:CreditCard)
            OPTIONAL MATCH (c)-[:HAS_FD]->(fd:FixedDeposit)
            OPTIONAL MATCH (c)-[:HAS_LOAN]->(l:Loan)
            OPTIONAL MATCH (c)-[:HAS_CLAIM]->(cl:Claim)
            OPTIONAL MATCH (clp:Policy)-[:HAS_CLAIM]->(cl)
            OPTIONAL MATCH (c)-[:HAS_POLICY]->(p:Policy)
            OPTIONAL MATCH (c)-[:HAS_INTERACTION]->(i:Interaction) WHERE i.status = 'open'
            OPTIONAL MATCH (c)-[:KYC_VERIFIED_BY]->(k:KYC)
            RETURN
                c.customer_id     AS customer_id,
                c.name            AS name,
                c.age             AS age,
                c.occupation      AS occupation,
                c.segment         AS segment,
                c.email           AS email,
                c.phone           AS phone,
                c.city            AS city,
                c.country         AS country,
                k.kyc_status      AS kyc_status,
                collect(DISTINCT {
                    account_number: a.account_number,
                    account_type:   a.account_type,
                    account_sub_type: a.account_sub_type,
                    status:         a.status,
                    avg_monthly_balance: a.avg_monthly_balance
                }) AS accounts,
                collect(DISTINCT {
                    card_id:      cc.card_id,
                    card_variant: cc.card_variant,
                    balance_due:  cc.balance_due,
                    min_amount_due: cc.min_amount_due,
                    dpd:          cc.dpd
                }) AS credit_cards,
                collect(DISTINCT {
                    fd_id:           fd.fd_id,
                    principal_amount: fd.principal_amount,
                    maturity_date:   fd.maturity_date,
                    status:          fd.status
                }) AS fixed_deposits,
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
                    policy_type:  clp.policy_type,
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
            "name": row.get("name"),
            "age": row.get("age"),
            "occupation": row.get("occupation"),
            "segment": row.get("segment"),
            "email": row.get("email"),
            "phone": row.get("phone"),
            "city": row.get("city"),
            "country": row.get("country"),
            "kyc_status": row.get("kyc_status", "Unknown"),
            "accounts": [a for a in (row.get("accounts") or []) if a.get("account_number")],
            "credit_cards": [cc for cc in (row.get("credit_cards") or []) if cc.get("card_id")],
            "fixed_deposits": [fd for fd in (row.get("fixed_deposits") or []) if fd.get("fd_id")],
            "loans": [l for l in (row.get("loans") or []) if l.get("loan_id")],
            "claims": [c for c in (row.get("claims") or []) if c.get("claim_id")],
            "policies": [p for p in (row.get("policies") or []) if p.get("policy_id")],
            "open_interactions": [i for i in (row.get("open_interactions") or []) if i.get("conversation_id")],
        }
    except Exception:
        logger.warning("neo4j_get_customer_360_failed", extra={"id": phone_or_email}, exc_info=True)
        return {}


# ── Resolution Memory ─────────────────────────────────────────────────────────

def search_resolution_memory(client, memory_key: str) -> dict | None:
    """Return a human-verified resolution for a memory_key ("intent:subtype").

    The key is the KIND OF PROBLEM, not one customer's account: keying on a
    customer's own loan/claim id (the previous behaviour) made every memory
    unreachable by anyone else, while the "general" fallback collided across
    unrelated matters. Keying on ticket_scope is what lets a resolution verified
    for one customer answer another customer's same problem.

    Returns None unless the memory is verified — an unverified memory is a
    candidate awaiting human approval, never a servable answer.
    """
    if client is None or not memory_key:
        return None
    try:
        rows = client.query(
            """
            MATCH (rm:ResolutionMemory {memory_key: $memory_key})
            WHERE coalesce(rm.verified, false) = true
            RETURN rm.resolution_text AS resolution,
                   rm.times_reused   AS times_reused,
                   rm.verified       AS verified,
                   rm.query_pattern  AS query_pattern
            ORDER BY rm.times_reused DESC
            LIMIT 1
            """,
            {"memory_key": memory_key},
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


def get_graph_schema(client) -> dict:
    """The SHAPE of the knowledge graph — node types and how they connect.

    Deliberately not a customer's records (that is customers.py::customer_graph_view).
    This answers "what does this system know how to know", so it returns one node per
    LABEL carrying its live count, not one node per row.

    Counts come from a full scan, which is honest at this size (167 nodes) and would
    not be at millions. If that ever matters, swap to
    `CALL apoc.meta.stats()` or the count-store.
    """
    if client is None:
        return {"nodes": [], "edges": [], "reachable": False}
    try:
        labels = client.query(
            "MATCH (n) UNWIND labels(n) AS l "
            "RETURN l AS label, count(*) AS count ORDER BY count DESC"
        )
        rels = client.query(
            "MATCH (a)-[r]->(b) "
            "RETURN labels(a)[0] AS source, type(r) AS rel, labels(b)[0] AS target, "
            "count(*) AS count ORDER BY count DESC"
        )
    except Exception as exc:
        return {"nodes": [], "edges": [], "reachable": False, "error": str(exc)[:200]}

    return {
        "reachable": True,
        "nodes": [{"id": r["label"], "label": r["label"], "count": r["count"]} for r in labels],
        "edges": [
            {"source": r["source"], "target": r["target"], "rel": r["rel"], "count": r["count"]}
            for r in rels if r.get("source") and r.get("target")
        ],
    }


# Label -> the property that carries a human-readable name, best first. Falls back to
# the label plus a short id, so a node never renders as a bare dot with no identity.
_GRAPH_NAME_PROPS = {
    "Customer": ("name", "customer_id"),
    "Account": ("account_type", "account_number"),
    "CreditCard": ("card_type", "card_id"),
    "FixedDeposit": ("fd_type", "fd_id"),
    "Loan": ("loan_type", "loan_id"),
    "Policy": ("policy_type", "policy_id"),
    "Claim": ("claim_type", "claim_id"),
    "Transaction": ("txn_type", "transaction_id"),
    "ChargePenalty": ("charge_type", "charge_id"),
    "Product": ("name", "product_id"),
    "Interaction": ("channel", "conversation_id"),
    "Ticket": ("intent", "ticket_id"),
    "ResolutionMemory": ("intent", "memory_key"),
    "Agent": ("name", "agent_id"),
    "KYC": ("status", "customer_id"),
}


def get_full_graph(client, limit: int = 3000) -> dict:
    """Every node and relationship in the graph, for the live graph view.

    Distinct from get_graph_schema (one node per LABEL, the system's shape) and from
    customers.py::customer_graph_view (one customer's neighbourhood). This is the whole
    database as it stands right now, so it GROWS as traffic runs: every inbound message
    adds an (:Interaction), its (:Ticket), a (:ResolutionMemory) and a [:HANDLED_BY]
    edge to the (:Agent) that answered it. A snapshot of a freshly wiped database is
    therefore the floor, not the shape.

    ``limit`` bounds each of the two queries independently. At demo scale (hundreds of
    nodes) it never binds; it exists so a runaway graph degrades to a partial picture
    instead of hanging the browser. ``truncated`` tells the caller which happened.
    """
    if client is None:
        return {"nodes": [], "edges": [], "reachable": False}
    try:
        rows = client.query(
            "MATCH (n) RETURN id(n) AS nid, labels(n)[0] AS label, properties(n) AS props "
            f"LIMIT {int(limit)}"
        )
        rels = client.query(
            "MATCH (a)-[r]->(b) RETURN id(a) AS source, id(b) AS target, type(r) AS rel "
            f"LIMIT {int(limit)}"
        )
    except Exception as exc:
        return {"nodes": [], "edges": [], "reachable": False, "error": str(exc)[:200]}

    nodes = []
    for r in rows:
        label = r.get("label") or "Node"
        props = r.get("props") or {}
        name_props = _GRAPH_NAME_PROPS.get(label, ())
        label_text = ""
        for p in name_props:
            val = props.get(p)
            if val not in (None, ""):
                label_text = str(val)
                break
        # Never send an embedding to the browser: ResolutionMemory carries a
        # resolution_embedding of hundreds of floats, which would dwarf the payload
        # and means nothing on screen.
        safe = {k: v for k, v in props.items()
                if not k.endswith("_embedding") and not isinstance(v, (list, dict))}
        nodes.append({
            "id": r["nid"],
            "type": label,
            "label": label_text or label,
            "props": safe,
        })

    node_ids = {n["id"] for n in nodes}
    # Drop edges whose endpoints fell outside the node LIMIT — a dangling edge would
    # otherwise draw to a node that is not on the canvas.
    edges = [
        {"source": r["source"], "target": r["target"], "rel": r["rel"]}
        for r in rels
        if r.get("source") in node_ids and r.get("target") in node_ids
    ]
    return {
        "reachable": True,
        "nodes": nodes,
        "edges": edges,
        "truncated": len(rows) >= int(limit) or len(rels) >= int(limit),
    }
