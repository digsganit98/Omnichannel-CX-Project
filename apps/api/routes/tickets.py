from fastapi import APIRouter, HTTPException

from shared.utils.in_memory_store import store

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("")
def list_tickets() -> list[dict]:
    return [ticket.model_dump() for ticket in store.tickets.values()]


@router.get("/{ticket_id}")
def get_ticket(ticket_id: str) -> dict:
    ticket = store.tickets.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket.model_dump()
