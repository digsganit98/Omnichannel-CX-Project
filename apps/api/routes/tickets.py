from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_auth
from services.ticket_service.ticket_manager import TicketManager
from shared.schemas.tickets import TicketStatus

router = APIRouter(prefix="/admin/tickets", tags=["admin"], dependencies=[Depends(require_admin_auth)])


class TicketComment(BaseModel):
    comment: str
    actor: str = "admin"


class TicketStatusUpdate(BaseModel):
    status: TicketStatus
    actor: str = "admin"


@router.get("")
def list_tickets() -> list[dict]:
    return get_repository().list_tickets()


@router.get("/{ticket_id}")
def get_ticket(ticket_id: str) -> dict:
    ticket = get_repository().get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.get("/{ticket_id}/events")
def list_ticket_events(ticket_id: str) -> list[dict]:
    if get_repository().get_ticket(ticket_id) is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return get_repository().list_ticket_events(ticket_id)


@router.post("/{ticket_id}/sync")
def sync_ticket(ticket_id: str) -> dict:
    try:
        return TicketManager(get_repository()).sync_ticket(ticket_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{ticket_id}/comments")
def add_ticket_comment(ticket_id: str, payload: TicketComment) -> dict:
    try:
        return TicketManager(get_repository()).add_comment(ticket_id, payload.comment, payload.actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{ticket_id}/status")
def update_ticket_status(ticket_id: str, payload: TicketStatusUpdate) -> dict:
    try:
        # Pass the graph client so resolving also updates the Ticket node — otherwise the
        # graph keeps the ticket 'open' and the model is still told about a closed case.
        return TicketManager(get_repository(), neo4j_client=_neo4j_client()).update_status(
            ticket_id, payload.status, payload.actor
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _neo4j_client():
    """None when the graph is unreachable/disabled — status updates must still work."""
    try:
        from services.neo4j_service.client import Neo4jClient
        return Neo4jClient()
    except Exception:
        return None
