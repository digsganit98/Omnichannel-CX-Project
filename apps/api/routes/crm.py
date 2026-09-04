from fastapi import APIRouter, Depends

from apps.api.dependencies.security import require_admin_auth
from services.crm_service.client import CRMClient

router = APIRouter(prefix="/admin/crm", tags=["admin"], dependencies=[Depends(require_admin_auth)])


@router.get("/status")
def crm_status() -> dict:
    crm = CRMClient()
    return {
        "provider": crm.provider,
        "configured": crm.configured,
        "base_url_configured": bool(crm.base_url),
        "project_key_configured": bool(crm.project_key),
    }
