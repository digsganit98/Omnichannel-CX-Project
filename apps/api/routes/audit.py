from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_auth
from services.observability_service import fetch_langfuse_trace_observations

router = APIRouter(prefix="/admin/audit-events", tags=["admin"], dependencies=[Depends(require_admin_auth)])


@router.get("")
def list_audit_events(correlation_id: str | None = None) -> list[dict]:
    return get_repository().list_audit_events(correlation_id)


@router.get("/runs")
def list_audit_runs(
    days: int = Query(default=14, ge=1, le=90),
    channel: str | None = None,
    status: str | None = Query(default=None, pattern="^(ok|failed)$"),
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return get_repository().list_audit_runs(
        days=days, channel=channel, status=status, search=search, limit=limit, offset=offset,
    )


@router.get("/runs/{correlation_id}")
def get_audit_run(correlation_id: str) -> dict:
    run = get_repository().get_audit_run(correlation_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    # A run's LLM calls all nest under one root span (see langfuse_workflow_trace in
    # graph.py), so every llm_usage_event for this run shares the same trace_id.
    trace_id = next(
        (
            (event.get("metadata") or {}).get("langfuse_trace_id")
            for event in run.get("llm_usage_events", [])
            if (event.get("metadata") or {}).get("langfuse_trace_id")
        ),
        None,
    )
    run["langfuse"] = fetch_langfuse_trace_observations(trace_id)
    return run
