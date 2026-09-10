from fastapi import APIRouter, Depends, Query

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_auth
from services.observability_service import langfuse_status

router = APIRouter(
    prefix="/admin/llm-observability",
    tags=["admin-llm-observability"],
    dependencies=[Depends(require_admin_auth)],
)


@router.get("/summary")
def llm_usage_summary(days: int = Query(default=7, ge=0, le=90)) -> dict:
    return get_repository().get_llm_usage_summary(days=days)


@router.get("/status")
def llm_observability_status(check_auth: bool = False) -> dict:
    return {"langfuse": langfuse_status(check_auth=check_auth)}


@router.get("/events")
def llm_usage_events(
    limit: int = Query(default=100, ge=1, le=500),
    correlation_id: str | None = None,
) -> list[dict]:
    return get_repository().list_llm_usage_events(limit=limit, correlation_id=correlation_id)
