from fastapi import APIRouter, Depends

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_auth

router = APIRouter(prefix="/admin/audit-events", tags=["admin"], dependencies=[Depends(require_admin_auth)])


@router.get("")
def list_audit_events(correlation_id: str | None = None) -> list[dict]:
    return get_repository().list_audit_events(correlation_id)
