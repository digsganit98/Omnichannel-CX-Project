import logging

from fastapi import APIRouter, Depends, HTTPException

from apps.api.dependencies.security import require_admin_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/neo4j", tags=["admin"], dependencies=[Depends(require_admin_key)])


@router.post("/reload")
def reload_bfsi_data() -> dict:
    """Load (or reload) bfsi.xlsx into Neo4j. Safe to call multiple times — uses MERGE."""
    try:
        from services.neo4j_service.client import Neo4jClient
        from services.neo4j_service.loader import load_bfsi_data
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j service unavailable: {exc}") from exc

    client = Neo4jClient()
    try:
        counts = load_bfsi_data(client)
    except Exception as exc:
        logger.exception("neo4j_reload_failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        client.close()

    return {"loaded": counts}
