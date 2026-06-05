import logging
from functools import lru_cache

from fastapi import APIRouter, Depends

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_key
from services.neo4j_service.client import Neo4jClient
from services.neo4j_service.queries import get_customer_by_identifier, get_claim_status, get_loan_status

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/customers",
    tags=["admin"],
    dependencies=[Depends(require_admin_key)],
)


@lru_cache
def _neo4j() -> Neo4jClient:
    return Neo4jClient()


@router.get("/{customer_id}/graph")
def customer_graph(customer_id: str) -> dict:
    """Return loan and claim counts for a customer by resolving via channel identifiers into Neo4j."""
    identifiers = get_repository().list_customer_identifiers(customer_id)
    if not identifiers:
        return {"loan_count": 0, "claim_count": 0, "identifiers": [], "registration_date": None}

    try:
        client = _neo4j()
        neo4j_cid = None
        registration_date = None
        for row in identifiers:
            customer = get_customer_by_identifier(client, row["identifier"])
            if customer:
                neo4j_cid = customer["customer_id"]
                registration_date = customer.get("registration_date")
                break

        if not neo4j_cid:
            return {"loan_count": 0, "claim_count": 0, "identifiers": identifiers, "registration_date": None}

        loans = get_loan_status(client, neo4j_cid)
        claims = get_claim_status(client, neo4j_cid)
        return {"loan_count": len(loans), "claim_count": len(claims), "identifiers": identifiers, "registration_date": registration_date}
    except Exception as exc:
        logger.warning("neo4j_graph_lookup_failed customer=%s: %s", customer_id, exc)
        return {"loan_count": 0, "claim_count": 0, "identifiers": identifiers, "registration_date": None}
