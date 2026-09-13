"""Admin routes for agent-assist recommendations (next-best-action, cross-sell, ...).

Recommendations are surfaced to a human agent for approval/dismissal — never sent to
a customer automatically. See services/agent_assist_service/next_best_action.py.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_auth
# NextBestActionEngine's four `if` rules no longer drive the card - case_advisor does -
# but the class stays imported and on disk: tests/test_agent_assist.py exercises each rule
# directly, and deleting it would break a passing suite for no gain.
from services.agent_assist_service.next_best_action import NextBestActionEngine
from services.agent_assist_service import case_advisor, opportunity_engine
from services.rag_service.groq_generator import GroqGenerator
from shared.schemas.agent_assist import ActionType, DRAFTABLE_ACTION_TYPES, NBADecisionUpdate
from shared.schemas.tickets import SERVICEABLE_TICKET_STATUSES

logger = logging.getLogger(__name__)

# Cross-sell/up-sell rows are "offers": Approve creates an editable reply draft
# (delivered over push channels), unlike operational NBA rows where Approve only
# records the decision.
_OFFER_ACTION_TYPES = {"cross_sell", "up_sell"}
# Marker channel on offer drafts — send_draft delivers these to ALL push
# channels (whatsapp + email) the customer has on record.
OFFER_DRAFT_CHANNEL = "offer"

router = APIRouter(prefix="/admin/agent-assist", tags=["admin"], dependencies=[Depends(require_admin_auth)])


def _advice_generator():
    """The model behind the Suggested Actions card. A seam, so tests can replace it."""
    return GroqGenerator()


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
    """What needs saying to this customer, decided by the LLM (see case_advisor).

    Replaces four hardcoded `if` rules that only ever fired on situations somebody had
    anticipated in advance. Those rules also had no UI for their whole life, so none of
    them was ever seen by anyone.
    """
    repository = get_repository()
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    customer_id = conversation.get("customer_id") or ""

    ticket = repository.get_ticket(ticket_id) if ticket_id else None
    if ticket is None:
        active = repository.find_active_ticket(conversation_id)
        ticket = active.model_dump(mode="json") if active else None

    turns = repository.list_conversation_turns(conversation_id)
    pending_drafts = repository.list_reply_drafts(
        conversation_id=conversation_id, status="pending")

    # Same degrade-gracefully graph lookup the offers route uses: no Neo4j means no
    # customer records in the prompt, not an error.
    graph_context = _graph_context_for(repository, customer_id)
    sentiment = _recent_sentiment(turns)
    promise = {
        "due_at": (ticket or {}).get("follow_up_due_at"),
        "overdue": _promise_overdue(ticket),
    }

    # Injectable so a test can stub the model instead of reaching for a real Groq call.
    # Without this seam the route reached GroqGenerator() directly and every test of it
    # depended on an API key being present - which in CI it is not, so the call failed,
    # llm_error was set, and no rows were persisted. The test was right and the route was
    # untestable; the fix belongs here rather than in a weakened assertion.
    advice = case_advisor.advise(
        generator=_advice_generator(),
        ticket=ticket,
        turns=turns,
        graph_context=graph_context,
        promise=promise,
        sentiment=sentiment,
        pending_drafts=pending_drafts,
    )
    llm_error = advice.get("llm_error")
    suppressed = advice.get("suppressed")

    pending = repository.list_agent_assist_recommendations(conversation_id=conversation_id, status="pending")
    existing_types = {row["action_type"] for row in pending}
    for action in advice.get("actions", []):
        if action["action_type"] in existing_types:
            continue
        pending.append(repository.add_agent_assist_recommendation(
            conversation_id=conversation_id,
            customer_id=customer_id,
            ticket_id=(ticket or {}).get("ticket_id"),
            action_type=action["action_type"],
            reason=action["reason"],
            confidence=action["confidence"],
            priority=0,
            # follow_up_due_at travels with the row so the CARD can compute the countdown
            # live on every render. The reason sentence carries the absolute date only
            # ("13 Sep, 10:21pm") because it is written once and read later - a stored
            # "8h left" is wrong by morning. Deadline is data; time remaining is derived.
            #
            # ONLY on a promise action. Attached to every action it rendered "7h left"
            # beside "CUSTOMER UPSET", which has no deadline of its own - a countdown
            # borrowed from a different fact, which is worse than no countdown at all.
            metadata=_action_metadata(action, ticket),
        ))

    # RETIRE what the rules no longer produce. The loop above only ever ADDED, so a row
    # outlived the condition that created it: measured on the live board, the follow-up
    # nudge was still on screen after the follow-up had been sent, because the rule had
    # correctly stopped firing while the row it wrote minutes earlier sat in the table
    # forever. The card reads the table, not the rules.
    #
    # Scoped to the action types THIS engine owns. /next-best-actions returns every pending
    # row for the conversation, offers included, and the NBA engine does not produce offers
    # - so an unscoped sweep would retire live cross-sell rows that nothing had decided.
    #
    # Only ever runs on a SUCCESSFUL engine pass. recommend() raising would leave `result`
    # unbound and this block unreached; an engine that returns nothing because it FAILED
    # must never be read as "nothing is outstanding" and erase the queue - the same failure
    # mode as a 429 cached as "no offers".
    #
    # SKIPPED ENTIRELY when the call failed or was gated. An engine that returned nothing
    # because it FAILED must never be read as "nothing is outstanding" - that would let one
    # rate-limited call silently empty a queue of real work, which is the trap recorded in
    # ec2-operations.md where a 429 cached as "no offers" and Refresh could not clear it.
    if not llm_error and not suppressed:
        still_current = {a["action_type"] for a in advice.get("actions", [])}
        for row in pending:
            action_type = row["action_type"]
            if action_type in _OFFER_ACTION_TYPES or action_type in still_current:
                continue
            repository.update_agent_assist_recommendation(
                row["recommendation_id"], status="superseded", actor="system",
            )
            row["status"] = "superseded"
    pending = [row for row in pending if row.get("status") == "pending"]

    # Do not surface recommendations tied to a ticket that is no longer active (resolved/
    # closed). A previously-saved 'pending' row lingers after its ticket is resolved; a done
    # ticket has no live action to take, so hide it. Conversation-level rows (no ticket_id)
    # are unaffected.
    _terminal = {"closed"}
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
        "conversation_id": conversation_id,
        "customer_id": customer_id,
        "ticket_id": (ticket or {}).get("ticket_id"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # Three distinct states, so the card can say which: items, deliberate silence, or
        # a failure. Rendering a failure as an empty list is what makes a broken check look
        # like a clean case.
        "suppressed": suppressed,
        "llm_error": llm_error,
        "actions": [r for r in pending if r.get("action_type") not in _OFFER_ACTION_TYPES],
    }


def _action_metadata(action: dict, ticket: dict | None) -> dict:
    """What travels with a recommendation row.

    The promise deadline goes ONLY on the action that is about the promise. Everything
    else gets `basis` alone, so the card shows a countdown exactly where one applies.
    """
    metadata = {"basis": action.get("basis")}
    if action["action_type"] in DRAFTABLE_ACTION_TYPES and (ticket or {}).get("follow_up_due_at"):
        metadata["follow_up_due_at"] = ticket["follow_up_due_at"]
    return metadata


def _graph_context_for(repository, customer_id: str) -> dict:
    """The customer's BFSI records, or {} when the graph is unreachable."""
    if not customer_id:
        return {}
    client = _try_neo4j()
    if not client:
        return {}
    try:
        from services.neo4j_service.queries import (
            get_customer_by_id, get_customer_by_identifier, get_customer_context_by_id,
        )
        for row in repository.list_customer_identifiers(customer_id):
            found = (get_customer_by_id(client, row["identifier"])
                     if row["channel"] == "graph"
                     else get_customer_by_identifier(client, row["identifier"]))
            if found:
                return get_customer_context_by_id(client, found["customer_id"]) or {}
    except Exception as exc:
        logger.warning("case_advice_graph_lookup_failed customer=%s: %s", customer_id, exc)
    return {}


def _recent_sentiment(turns: list[dict]) -> str | None:
    """Sentiment over the last five inbound turns, as the right panel reports it.

    Read from the sentiment already stored on each turn by the intent classifier - not
    re-derived here, so the card and the panel beside it cannot disagree.
    """
    inbound = [t for t in turns if t.get("direction") == "inbound"][-5:]
    if not inbound:
        return None
    negative = sum(1 for t in inbound
                   if ((t.get("metadata") or {}).get("sentiment") or "").lower() == "negative")
    if not negative:
        return "neutral or positive"
    pct = round(negative / len(inbound) * 100)
    label = "very frustrated" if pct >= 60 else "some frustration"
    return f"{label} ({pct}% negative across the last {len(inbound)} messages)"


def _promise_overdue(ticket: dict | None) -> bool:
    due_at = (ticket or {}).get("follow_up_due_at")
    if not due_at:
        return False
    try:
        return datetime.now(timezone.utc) > datetime.fromisoformat(due_at)
    except (TypeError, ValueError):
        return False


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
    # SERVICEABLE only. len(tickets) feeds the cache fingerprint below, so counting LOGGED
    # ids - which the redesign now creates for EVERY customer query - would change the
    # fingerprint on every message and re-run the engine's ~1000-token LLM call on the next
    # render. check_gates takes the list but does not read it (sentiment-only since
    # 2026-07-23), so this only affects the fingerprint and the engine's own ticket view.
    tickets = [
        t for t in repository.list_tickets()
        if t.get("customer_id") == customer_id
        and str(t.get("status") or "").lower() in SERVICEABLE_TICKET_STATUSES
    ]
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

    # Cache guard. This endpoint is called on EVERY right-panel render, including the
    # inbox poll's, and the engine's LLM call costs ~1000 tokens whether or not it finds
    # anything - measured at 53 calls in one day with zero customer messages. Re-run only
    # when something that could change the answer has changed: the customer's graph
    # records, how many turns they have, or which offers were already suggested.
    fingerprint = json.dumps(
        {"graph": graph_context, "turns": len(turns), "tickets": len(tickets),
         "suggested": sorted(already_suggested)},
        sort_keys=True, default=str,
    )
    input_hash = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    cached = repository.get_opportunity_evaluation(conversation_id)
    if cached and cached.get("input_hash") == input_hash:
        # Already evaluated on these exact inputs. Serve what it produced - which is
        # legitimately nothing when the model found no offer worth making.
        if cached.get("suppressed"):
            return {"conversation_id": conversation_id, "customer_id": customer_id,
                    "suppressed": cached["suppressed"], "opportunities": []}
        return {"conversation_id": conversation_id, "customer_id": customer_id,
                "suppressed": None, "opportunities": _pending_offers()}

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

    # Record that this evaluation ran, whatever it produced — including nothing. Without
    # this the no-offer case leaves no trace and re-runs on every render forever.
    try:
        repository.save_opportunity_evaluation(
            conversation_id, input_hash, result.get("suppressed"))
    except Exception:
        logger.exception("opportunity_evaluation_save_failed")  # serve it anyway

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


def _build_follow_up_draft(repository, recommendation: dict) -> dict:
    """Create an editable follow-up draft grounded in what we actually promised.

    The text is assembled from the record rather than generated: the promise itself is in
    the reply we already sent, the ticket carries the case, and an LLM call here would cost
    requests against the binding Groq limit to restate facts we hold. The agent edits it in
    the same draft card they already use, so the wording is theirs before it is sent.
    """
    conversation_id = recommendation.get("conversation_id") or ""
    ticket_id = recommendation.get("ticket_id")
    ticket = repository.get_ticket(ticket_id) if ticket_id else None

    # Reply on the channel the customer used, threaded onto their last inbound message.
    turns = repository.list_conversation_turns(conversation_id)
    inbound = [t for t in turns if t.get("direction") == "inbound"]
    last_inbound = inbound[-1] if inbound else None
    channel = (last_inbound or {}).get("channel") or "web_chat"

    subject = (ticket or {}).get("title") or "your request"
    reference = ticket_id or conversation_id
    draft_text = (
        "Hello,\n\n"
        f"I am following up on {subject.lower()} (reference {reference}), which we told you "
        "we would come back to you about.\n\n"
        "[Add the update here before sending.]\n\n"
        "Thank you for your patience."
    )
    return repository.add_reply_draft(
        conversation_id=conversation_id,
        customer_id=recommendation.get("customer_id") or "",
        channel=channel,
        draft_text=draft_text,
        ticket_id=ticket_id,
        inbound_turn_id=(last_inbound or {}).get("turn_id"),
        hold_reason="Promised follow-up — edit & send",
        reason_code=recommendation.get("action_type") or ActionType.PROMISED_UPDATE.value,
        channel_identifier=None,
        provider="follow_up_nudge",
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

    # Approving a FOLLOW-UP also executes something: an editable draft in the conversation's
    # OWN thread. Deliberately not the offer path - an offer fans out to every push channel
    # on record, whereas a follow-up belongs in the thread where the promise was made, on
    # the channel the customer used.
    if payload.status == "approved" and existing.get("action_type") in DRAFTABLE_ACTION_TYPES:
        conversation_id = existing.get("conversation_id") or ""
        pending_drafts = repository.list_reply_drafts(
            conversation_id=conversation_id, status="pending")
        if pending_drafts:
            raise HTTPException(
                status_code=409,
                detail="A pending reply draft already exists — send or discard it first.")
        draft = _build_follow_up_draft(repository, existing)

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
