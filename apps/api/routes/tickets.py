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


class TicketAssign(BaseModel):
    # None clears the owner and returns the ticket to triage.
    assignee: str | None = None
    actor: str = "admin"


class TicketApproval(BaseModel):
    approved: bool
    actor: str = "admin"
    note: str = ""


class TicketClose(BaseModel):
    reason: str
    actor: str = "admin"


@router.get("")
def list_tickets() -> list[dict]:
    """Every ticket, each carrying the CONTACTS made on it.

    `contacts` is attached here rather than inside repository.list_tickets() because this
    route is the Service Desk board and the other five callers of list_tickets() do not want
    the extra scan. Without it the board cannot show a case as a sequence: the ticket row
    records when we FIRST answered and nothing about the times we went back afterwards, so a
    fraud dispute we had updated three times rendered as one timestamp and two dashes.
    """
    repository = get_repository()
    contacts = repository.list_ticket_contacts()
    # `open_actions` carries the one thing the ticket row cannot: whether the case is blocked
    # on the CUSTOMER. See list_open_action_types - without it the board has no honest way to
    # say "waiting on them", and defaults every case to us.
    open_actions = repository.list_open_action_types()
    tickets = repository.list_tickets()
    for ticket in tickets:
        ticket["contacts"] = contacts.get(ticket["ticket_id"], [])
        ticket["open_actions"] = open_actions.get(ticket["ticket_id"], [])
    return tickets


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


@router.patch("/{ticket_id}/assign")
def assign_ticket(ticket_id: str, payload: TicketAssign) -> dict:
    repository = get_repository()
    # An unknown username would write a ticket nobody can see in any queue - it would not
    # match a roster row, so the board would show an owner that does not exist. Validate
    # against the roster rather than trusting the caller.
    if payload.assignee is not None:
        known = {a["username"] for a in repository.list_agents()}
        if payload.assignee not in known:
            raise HTTPException(status_code=400, detail=f"Unknown assignee: {payload.assignee}")
    try:
        return TicketManager(repository).assign(ticket_id, payload.assignee, payload.actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{ticket_id}/approval")
def decide_approval(ticket_id: str, payload: TicketApproval) -> dict:
    try:
        return TicketManager(get_repository()).set_approval(
            ticket_id, payload.approved, payload.actor, payload.note
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{ticket_id}/close")
def close_ticket(ticket_id: str, payload: TicketClose) -> dict:
    reason = (payload.reason or "").strip()
    # A closure with no reason is the thing this endpoint exists to prevent: closing is a
    # human judgement and the record has to say what it was.
    if not reason:
        raise HTTPException(status_code=400, detail="A closure reason is required")
    try:
        return TicketManager(get_repository(), neo4j_client=_neo4j_client()).close(
            ticket_id, reason, payload.actor
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
