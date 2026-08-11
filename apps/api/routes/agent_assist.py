"""Admin routes for agent-assist recommendations (next-best-action, cross-sell, ...).

Recommendations are surfaced to a human agent for approval/dismissal — never sent to
a customer automatically. See services/agent_assist_service/next_best_action.py.
"""

import os

from fastapi import APIRouter, Depends, HTTPException

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_key
from services.agent_assist_service.next_best_action import NextBestActionEngine
from shared.schemas.agent_assist import NBADecisionUpdate

router = APIRouter(prefix="/admin/agent-assist", tags=["admin"], dependencies=[Depends(require_admin_key)])


def _try_neo4j():
    """Best-effort Neo4j client — recommendations degrade gracefully without one."""
    try:
        if os.getenv("NEO4J_ENABLED", "true").lower() != "true":
            return None
        from services.neo4j_service.client import Neo4jClient
        return Neo4jClient()
    except Exception:
        return None


@router.get("/next-best-actions")
def get_next_best_actions(conversation_id: str, ticket_id: str | None = None) -> dict:
    repository = get_repository()
    engine = NextBestActionEngine(repository, neo4j_client=_try_neo4j())
    result = engine.recommend(conversation_id, ticket_id=ticket_id)

    pending = repository.list_agent_assist_recommendations(conversation_id=conversation_id, status="pending")
    existing_types = {row["action_type"] for row in pending}
    for action in result.actions:
        if action.action_type.value in existing_types:
            continue
        pending.append(repository.add_agent_assist_recommendation(
            conversation_id=result.conversation_id,
            customer_id=result.customer_id,
            ticket_id=result.ticket_id,
            action_type=action.action_type.value,
            reason=action.reason,
            confidence=action.confidence,
            priority=action.priority,
            metadata=action.metadata,
        ))

    # Do not surface recommendations tied to a ticket that is no longer active (resolved/
    # closed). A previously-saved 'pending' row lingers after its ticket is resolved; a done
    # ticket has no live action to take, so hide it. Conversation-level rows (no ticket_id)
    # are unaffected.
    _terminal = {"resolved", "closed"}
    _ticket_status: dict[str, str | None] = {}

    def _is_active(ticket_id: str | None) -> bool:
        if not ticket_id:
            return True
        if ticket_id not in _ticket_status:
            t = repository.get_ticket(ticket_id)
            _ticket_status[ticket_id] = (t or {}).get("status")
        return _ticket_status[ticket_id] not in _terminal

    pending = [row for row in pending if _is_active(row.get("ticket_id"))]

    return {
        "conversation_id": result.conversation_id,
        "customer_id": result.customer_id,
        "ticket_id": result.ticket_id,
        "generated_at": result.generated_at.isoformat(),
        "actions": pending,
    }


@router.get("/recommendations")
def list_recommendations(ticket_id: str | None = None, conversation_id: str | None = None) -> list[dict]:
    return get_repository().list_agent_assist_recommendations(
        ticket_id=ticket_id, conversation_id=conversation_id,
    )


@router.post("/recommendations/{recommendation_id}/decision")
def decide_recommendation(recommendation_id: str, payload: NBADecisionUpdate) -> dict:
    repository = get_repository()
    updated = repository.update_agent_assist_recommendation(
        recommendation_id, status=payload.status, actor=payload.actor,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    repository.add_audit_event(
        "nba_recommendation_" + payload.status,
        recommendation_id,
        customer_id=updated.get("customer_id"),
        conversation_id=updated.get("conversation_id"),
        ticket_id=updated.get("ticket_id"),
        details={"action_type": updated.get("action_type"), "actor": payload.actor},
    )
    return updated
