"""Admin routes for Neo4j graph database: load BFSI data and inspect graph status."""

from fastapi import APIRouter, HTTPException

from apps.api.dependencies.security import require_admin_auth
from fastapi import Depends

router = APIRouter(
    prefix="/admin/neo4j",
    tags=["admin"],
    dependencies=[Depends(require_admin_auth)],
)


def _get_client():
    try:
        from services.neo4j_service.client import Neo4jClient
        return Neo4jClient()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j client unavailable: {exc}") from exc


@router.post("/load")
def load_bfsi_data() -> dict:
    """Load (or reload) the BFSI Excel data into the Neo4j graph.

    Uses MERGE so it is safe to call multiple times — existing nodes are updated,
    not duplicated.
    """
    client = _get_client()
    try:
        from services.neo4j_service.loader import load_bfsi_data as _load
        counts = _load(client)
        return {"status": "loaded", "counts": counts}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        client.close()


@router.get("/status")
def graph_status() -> dict:
    """Return Neo4j reachability and node/relationship counts."""
    client = _get_client()
    try:
        base = client.status()
        if not base.get("reachable"):
            return base

        node_counts = _count_nodes(client)
        rel_counts = _count_relationships(client)
        return {**base, "node_counts": node_counts, "relationship_counts": rel_counts}
    finally:
        client.close()


@router.post("/setup-indexes")
def setup_vector_indexes() -> dict:
    """Create Neo4j vector indexes on ResolutionMemory and Interaction nodes.

    Requires Neo4j 5.11+. Safe to call multiple times (IF NOT EXISTS guard).
    """
    client = _get_client()
    try:
        from services.neo4j_service.query_library import create_vector_indexes
        result = create_vector_indexes(client)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        client.close()


@router.get("/cross-sell-candidates")
def cross_sell_candidates(limit: int = 50) -> dict:
    """Return customers with loans but no life/term insurance — cross-sell opportunity."""
    client = _get_client()
    try:
        from services.neo4j_service.query_library import get_cross_sell_candidates
        candidates = get_cross_sell_candidates(client, limit=limit)
        return {"count": len(candidates), "candidates": candidates}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        client.close()


@router.get("/schema")
def graph_schema() -> dict:
    """The knowledge graph's SHAPE — node types and how they connect, with live counts.

    Distinct from /admin/customers/{id}/graph-view, which draws one customer's records.
    This answers "what does this system know how to know".
    """
    client = _get_client()
    try:
        from services.neo4j_service.query_library import get_graph_schema
        return get_graph_schema(client)
    finally:
        client.close()


@router.get("/graph")
def full_graph(limit: int = 3000) -> dict:
    """Every node and relationship currently in the graph, for the live graph view.

    /schema answers "what does this system know how to know" (one node per label).
    This answers "what does it hold right now" — and it grows with traffic, because
    each message writes an :Interaction, its :Ticket, a :ResolutionMemory and a
    :HANDLED_BY edge to the answering :Agent.
    """
    client = _get_client()
    try:
        from services.neo4j_service.query_library import get_full_graph
        return get_full_graph(client, limit=limit)
    finally:
        client.close()


def _count_nodes(client) -> dict:
    labels = ["Customer", "Account", "CreditCard", "FixedDeposit", "Loan", "Claim",
              "Transaction", "ChargePenalty", "Product", "Policy", "KYC",
              "Agent", "Interaction", "Ticket", "ResolutionMemory"]
    counts = {}
    for label in labels:
        try:
            rows = client.query(f"MATCH (n:{label}) RETURN count(n) AS total")
            counts[label] = rows[0]["total"] if rows else 0
        except Exception:
            counts[label] = 0
    return counts


def _count_relationships(client) -> dict:
    rel_types = ["HAS_ACCOUNT", "HAS_CREDIT_CARD", "HAS_FD", "HAS_LOAN", "HAS_CLAIM",
                 "HAS_POLICY", "HAS_TRANSACTION", "HAS_CHARGE", "HAS_INTERACTION",
                 "HAS_TICKET", "KYC_VERIFIED_BY", "PRODUCT_IS",
                 "CREATED_MEMORY", "HANDLED_BY"]
    counts = {}
    for rel in rel_types:
        try:
            rows = client.query(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS total")
            counts[rel] = rows[0]["total"] if rows else 0
        except Exception:
            counts[rel] = 0
    return counts
