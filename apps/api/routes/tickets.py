from fastapi import APIRouter, Depends, HTTPException

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_key

router = APIRouter(prefix="/admin/tickets", tags=["admin"], dependencies=[Depends(require_admin_key)])


@router.get("")
def list_tickets() -> list[dict]:
    return get_repository().list_tickets()


@router.get("/{ticket_id}")
def get_ticket(ticket_id: str) -> dict:
    ticket = get_repository().get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket
