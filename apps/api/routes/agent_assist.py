"""Admin routes for agent-assist recommendations (next-best-action, cross-sell, ...).

Recommendations are surfaced to a human agent for approval/dismissal — never sent to
a customer automatically. See services/agent_assist_service/next_best_action.py.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_key
from services.agent_assist_service.next_best_action import NextBestActionEngine
from services.agent_assist_service import opportunity_engine
from shared.schemas.agent_assist import NBADecisionUpdate

logger = logging.getLogger(__name__)

# Cross-sell/up-sell rows are "offers": Approve creates an editable reply draft
# (delivered over push channels), unlike operational NBA rows where Approve only
# records the decision.
_OFFER_ACTION_TYPES = {"cross_sell", "up_sell"}
# Marker channel on offer drafts — send_draft delivers these to ALL push
# channels (whatsapp + email) the customer has on record.
OFFER_DRAFT_CHANNEL = "offer"

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


@router.get("/opportunities")
def get_opportunities(conversation_id: str) -> dict:
    """Cross-sell/up-sell opportunities for a conversation (LLM-selected from a
    code-built candidate set, code-gated; see opportunity_engine). Persists new
    items as pending agent_assist_recommendations rows; returns pending rows.
    """
    repository = get_repository()
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    customer_id = conversation.get("customer_id") or ""

    def _pending_offers() -> list[dict]:
        rows = repository.list_agent_assist_recommendations(
            conversation_id=conversation_id, status="pending")
        return [r for r in rows if r.get("action_type") in _OFFER_ACTION_TYPES]

    # Resolve the BFSI graph customer + context (same degrade-gracefully pattern
    # as the NBA engine — no Neo4j means no candidates, not an error).
    client = _try_neo4j()
    customer: dict = {}
    graph_context: dict = {}
    charges: list[dict] = []
    if client and customer_id:
        try:
            from services.neo4j_service.queries import (
                get_charges, get_customer_by_id, get_customer_by_identifier,
                get_customer_context_by_id,
            )
            for row in repository.list_customer_identifiers(customer_id):
                found = (get_customer_by_id(client, row["identifier"])
                         if row["channel"] == "graph"
                         else get_customer_by_identifier(client, row["identifier"]))
                if found:
                    customer = found
                    graph_context = get_customer_context_by_id(client, found["customer_id"]) or {}
                    charges = get_charges(client, found["customer_id"]) or []
                    break
        except Exception as exc:
            logger.warning("opportunity_graph_lookup_failed conv=%s: %s", conversation_id, exc)
    if not graph_context:
        return {"conversation_id": conversation_id, "customer_id": customer_id,
                "suppressed": None, "opportunities": _pending_offers()}

    # Conversation-side inputs. list_customer_turns returns newest-first; the
    # engine (and its prompt) expect chronological order — normalize here.
    tickets = [t for t in repository.list_tickets() if t.get("customer_id") == customer_id]
    turns = list(reversed(repository.list_customer_turns(customer_id)))

    # "Do not repeat": every offer already suggested for this conversation,
    # whatever its decision — a dismissed offer stays retired.
    all_rows = repository.list_agent_assist_recommendations(conversation_id=conversation_id)
    suggested_products = {
        (r.get("metadata") or {}).get("product")
        for r in all_rows if r.get("action_type") in _OFFER_ACTION_TYPES
    } - {None}
    already_suggested = [
        f"{(r.get('metadata') or {}).get('product')}: {r.get('reason') or ''}"
        for r in all_rows if r.get("action_type") in _OFFER_ACTION_TYPES
    ]

    from services.rag_service.groq_generator import GroqGenerator
    result = opportunity_engine.generate_opportunities(
        generator=GroqGenerator(),
        customer=customer,
        graph_context=graph_context,
        tickets=tickets,
        turns=turns,
        already_suggested=already_suggested,
        charges=charges,
    )

    if result.get("suppressed"):
        return {"conversation_id": conversation_id, "customer_id": customer_id,
                "suppressed": result["suppressed"], "opportunities": []}

    # Persist new items; dedupe by product against EVERY prior row (pending,
    # approved, dismissed) so nothing resurfaces after a decision.
    for opp in result.get("opportunities") or []:
        if opp["product"] in suggested_products:
            continue
        repository.add_agent_assist_recommendation(
            conversation_id=conversation_id,
            customer_id=customer_id,
            ticket_id=None,
            action_type=opp["kind"],
            reason=opp["pitch"],
            confidence=opp["confidence"],
            priority=5,
            metadata={"product": opp["product"], "basis": opp["basis"],
                      "why_now": opp["reason"], "source": "opportunity_engine"},
        )

    return {"conversation_id": conversation_id, "customer_id": customer_id,
            "suppressed": None, "opportunities": _pending_offers()}


@router.get("/recommendations")
def list_recommendations(ticket_id: str | None = None, conversation_id: str | None = None) -> list[dict]:
    return get_repository().list_agent_assist_recommendations(
        ticket_id=ticket_id, conversation_id=conversation_id,
    )


@router.post("/recommendations/{recommendation_id}/decision")
def decide_recommendation(recommendation_id: str, payload: NBADecisionUpdate) -> dict:
    repository = get_repository()
    existing = repository.get_agent_assist_recommendation(recommendation_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    # Approving an OFFER executes something: it creates an editable reply draft
    # (the existing HIL draft-card flow) that the agent reviews and sends — the
    # send then delivers to every push channel (WhatsApp/email) on record.
    # Validate preconditions BEFORE flipping the recommendation status.
    draft = None
    if payload.status == "approved" and existing.get("action_type") in _OFFER_ACTION_TYPES:
        conversation_id = existing.get("conversation_id") or ""
        customer_id = existing.get("customer_id") or ""
        identifiers = repository.list_customer_identifiers(customer_id)
        push = [i for i in identifiers if i["channel"] in ("whatsapp", "email")]
        if not push:
            raise HTTPException(
                status_code=400,
                detail="Customer has no WhatsApp or email on record to deliver an offer.")
        pending_drafts = repository.list_reply_drafts(
            conversation_id=conversation_id, status="pending")
        if pending_drafts:
            raise HTTPException(
                status_code=409,
                detail="A pending reply draft already exists — send or discard it first.")
        # Carry the offer's product (health_insurance, credit_card, …) onto the
        # draft so the sent offer turn can be grouped by its own theme in the
        # conversation view (matching topic group, else its own group).
        offer_product = (existing.get("metadata") or {}).get("product")
        draft = repository.add_reply_draft(
            conversation_id=conversation_id,
            customer_id=customer_id,
            channel=OFFER_DRAFT_CHANNEL,
            draft_text=existing.get("reason") or "",  # the pitch, editable by the agent
            hold_reason="Approved offer — review & send",
            reason_code=existing.get("action_type") or "cross_sell",
            channel_identifier=None,
            provider="opportunity_engine",
            offer_product=offer_product,
        )

    updated = repository.update_agent_assist_recommendation(
        recommendation_id, status=payload.status, actor=payload.actor,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if draft is not None:
        updated = {**updated, "draft_id": draft.get("draft_id")}
    repository.add_audit_event(
        "nba_recommendation_" + payload.status,
        recommendation_id,
        customer_id=updated.get("customer_id"),
        conversation_id=updated.get("conversation_id"),
        ticket_id=updated.get("ticket_id"),
        details={"action_type": updated.get("action_type"), "actor": payload.actor},
    )
    return updated
