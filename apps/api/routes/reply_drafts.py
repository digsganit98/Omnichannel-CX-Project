"""Admin routes for human-in-the-loop reply drafts.

When the review gate holds an AI reply (see services/workflow_service/review_gate.py), the
AI's answer is stored as a pending draft. An admin lists held drafts, edits the text, and
sends it manually — which delivers to the customer (WhatsApp/email push; web-chat via the
portal's history poll) and persists a normal outbound turn.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_key
from services.channel_service.delivery import OutboundDeliveryService
from shared.schemas.messages import Channel, InboundMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/reply-drafts", tags=["admin"], dependencies=[Depends(require_admin_key)])


class SendDraftRequest(BaseModel):
    text: str            # final text the agent sends (may differ from the AI draft)
    actor: str = "admin"


class DiscardDraftRequest(BaseModel):
    actor: str = "admin"


@router.get("")
def list_drafts(conversation_id: str | None = None, status: str = "pending") -> list[dict]:
    # status="" (empty) returns all statuses
    return get_repository().list_reply_drafts(
        conversation_id=conversation_id, status=status or None,
    )


@router.post("/{draft_id}/send")
def send_draft(draft_id: str, payload: SendDraftRequest) -> dict:
    repository = get_repository()
    draft = repository.get_reply_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Draft already {draft['status']}")

    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Reply text is required")

    # Offer drafts (channel="offer", created when an admin approves a cross-sell/
    # up-sell opportunity) are proactive outbound, not replies: deliver to EVERY
    # push channel the customer has on record (WhatsApp and/or email — real banks
    # send offers on both), never web chat. One outbound turn per delivery.
    if draft["channel"] == "offer":
        return _send_offer_draft(repository, draft, draft_id, text, payload.actor)

    # Deliver to the customer over the same channel the held query arrived on. Web-chat has
    # no push provider — delivery.send() returns a synchronous "sent" and the customer sees
    # the reply on the portal's next history poll (persisted as the outbound turn below).
    try:
        channel = Channel(draft["channel"])
    except ValueError:
        channel = Channel.WEB_CHAT

    # Thread the reply into the original conversation. For email, delivery.send() sets the
    # In-Reply-To/References headers from external_message_id and the "Re: <subject>" from
    # subject — so carry the ORIGINAL inbound email's real Message-ID + subject here (not the
    # internal turn id), otherwise Gmail shows the agent's reply as a separate mail.
    inbound_turn = repository.get_turn(draft["inbound_turn_id"]) if draft.get("inbound_turn_id") else None
    reply_subject = (inbound_turn or {}).get("subject")
    reply_to_message_id = (inbound_turn or {}).get("external_message_id") or draft.get("inbound_turn_id")

    outbound_message = InboundMessage(
        channel=channel,
        channel_identifier=draft.get("channel_identifier") or "",
        text="",
        provider=draft.get("provider") or "manual_agent_reply",
        subject=reply_subject,
        correlation_id=draft_id,
        external_message_id=reply_to_message_id,
    )
    delivery = OutboundDeliveryService().send(outbound_message, text)

    # Persist the agent's reply as a normal outbound turn so it shows in the inbox and the
    # customer portal (portal shows web_chat turns only — the channel is preserved here).
    turn = repository.append_turn(
        conversation_id=draft["conversation_id"],
        customer_id=draft["customer_id"],
        channel=draft["channel"],
        direction="outbound",
        text=text,
        ticket_id=draft.get("ticket_id"),
        delivery_status=delivery.get("status", "sent"),
        metadata={"source": "manual_agent_reply", "draft_id": draft_id, "actor": payload.actor},
    )

    _carry_retrieval_evidence(repository, draft, turn["turn_id"])

    updated = repository.update_reply_draft(
        draft_id, status="sent", actor=payload.actor, sent_text=text,
    )
    edited = text != (draft.get("draft_text") or "")

    # Feed the agent's verdict back to the graph. Reviewing a held reply IS a human
    # judgement on that answer — sent unedited endorses it, rewritten rejects it — and
    # until now that judgement was recorded in the audit row below and read by nothing,
    # so every ResolutionMemory stayed unverified and therefore unservable forever.
    # Best-effort: a graph failure must never block a reply the agent has approved.
    memory = _verify_resolution_memory(draft, text, edited)
    # A person read this reply and pressed send, so the graph must say so. The message
    # path records the AI as handler (it drafted the text); without this the human's
    # review was invisible and HUMAN_SR sat at zero interactions.
    _record_human_handling(draft, edited)

    repository.add_audit_event(
        "reply_draft_sent",
        draft_id,
        customer_id=draft.get("customer_id"),
        conversation_id=draft.get("conversation_id"),
        ticket_id=draft.get("ticket_id"),
        details={"actor": payload.actor, "delivery_status": delivery.get("status"),
                 "edited": edited,
                 "memory_id": (memory or {}).get("memory_id"),
                 "memory_verified": (memory or {}).get("verified")},
    )
    return {"draft": updated, "turn_id": turn["turn_id"], "delivery": delivery,
            "memory": memory}


def _neo4j_client():
    """None when the graph is unreachable/disabled — sending a reply must still work."""
    try:
        from services.neo4j_service.client import Neo4jClient
        return Neo4jClient()
    except Exception:
        return None


def _verify_resolution_memory(draft: dict, sent_text: str, edited: bool) -> dict | None:
    """Mark the memory this draft's answer created as human-verified (or not).

    The draft carries no memory id, and none needs to be added: inbound_turn_id is the
    :Interaction key, and the interaction already points at the memory it created.
    """
    turn_id = draft.get("inbound_turn_id")
    if not turn_id:
        return None
    try:
        from services.neo4j_service import writer as neo4j_writer
        return neo4j_writer.verify_resolution_memory(
            _neo4j_client(), turn_id=turn_id, approved_text=sent_text, edited=edited,
        )
    except Exception:
        logger.warning("resolution_memory_verify_failed", extra={"draft_id": draft.get("draft_id")},
                       exc_info=True)
        return None


def _record_human_handling(draft: dict, edited: bool) -> dict | None:
    """Mark this turn's Interaction as handled by a human (and edited, when reworded)."""
    turn_id = draft.get("inbound_turn_id")
    if not turn_id:
        return None
    try:
        from services.neo4j_service import writer as neo4j_writer
        return neo4j_writer.record_human_handling(_neo4j_client(), turn_id=turn_id, edited=edited)
    except Exception:
        logger.warning("human_handling_record_failed", extra={"draft_id": draft.get("draft_id")},
                       exc_info=True)
        return None


def _carry_retrieval_evidence(repository, draft: dict, sent_turn_id: str) -> None:
    """Copy the held reply's retrieval evidence onto the turn the agent actually sent.

    Evidence is written once, against the outbound turn that exists at reply time
    (graph.py). When the review gate holds, that turn is the HOLDING message
    ("Support Agent will help you shortly…") — so the real reply, created here on
    approval, carries no evidence at all. The provenance endpoint then falls back to
    inferring the source from the intent label, which over-claims: a transactional
    intent whose customer has no such record answers from the KB, yet the panel would
    still report "graph".

    The held answer and the holding message come from the same resolution, so the
    holding turn's evidence describes the sent text. Locate it as the first outbound
    turn after the draft's inbound turn (turns are chronological).

    Best-effort: a failure here must never block a delivered reply, and duplicate
    evidence is avoided by skipping turns that already have some.
    """
    inbound_turn_id = draft.get("inbound_turn_id")
    if not inbound_turn_id:
        return
    try:
        if repository.list_retrieval_evidence(sent_turn_id):
            return
        turns = repository.list_conversation_turns(draft["conversation_id"])
        holding_turn_id = None
        seen_inbound = False
        for turn in turns:
            if turn["turn_id"] == inbound_turn_id:
                seen_inbound = True
                continue
            if not seen_inbound:
                continue
            if turn["turn_id"] == sent_turn_id:
                break
            if turn.get("direction") == "outbound":
                holding_turn_id = turn["turn_id"]
                break
        if not holding_turn_id:
            return
        evidence = repository.list_retrieval_evidence(holding_turn_id) or []
        contexts = [
            {
                "text": item.get("chunk_text") or "",
                "score": item.get("score") or 0.0,
                "metadata": item.get("metadata") or {},
            }
            for item in evidence
        ]
        if contexts:
            repository.add_retrieval_evidence(sent_turn_id, contexts)
    except Exception:
        pass


_OFFER_EMAIL_SUBJECT = "An offer curated for you"


def _push_dedupe_key(identity: dict) -> str:
    """Normalized destination key so the same person isn't messaged twice.

    A customer can carry the same WhatsApp number stored both bare and with the
    country code (e.g. '7890864700' and '917890864700'), because the inbound
    path only does `.lstrip('+')`. Collapse to digits and drop a leading Indian
    country code (91) so both rows map to one destination. Email is keyed by
    lowercased address.
    """
    channel = identity.get("channel")
    ident = (identity.get("identifier") or "").strip()
    if channel == "email":
        return f"email:{ident.lower()}"
    digits = "".join(c for c in ident if c.isdigit())
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[2:]
    return f"whatsapp:{digits}"


def _dedupe_push_identifiers(push: list[dict]) -> list[dict]:
    """Keep the first identifier per normalized destination (order preserved)."""
    seen: set[str] = set()
    unique: list[dict] = []
    for identity in push:
        key = _push_dedupe_key(identity)
        if key not in seen:
            seen.add(key)
            unique.append(identity)
    return unique


def _send_offer_draft(repository, draft: dict, draft_id: str, text: str, actor: str) -> dict:
    """Deliver an approved offer to every push channel on record (whatsapp/email).

    A missing channel is skipped; at least one identifier is guaranteed because
    the approve endpoint refuses to create an offer draft without one.
    """
    identifiers = repository.list_customer_identifiers(draft.get("customer_id") or "")
    push = _dedupe_push_identifiers(
        [i for i in identifiers if i["channel"] in ("whatsapp", "email")]
    )
    if not push:
        raise HTTPException(
            status_code=400,
            detail="Customer has no WhatsApp or email on record to deliver this offer.")

    delivery_service = OutboundDeliveryService()
    deliveries: list[dict] = []
    turn_ids: list[str] = []
    for identity in push:
        channel = Channel(identity["channel"])
        outbound_message = InboundMessage(
            channel=channel,
            channel_identifier=identity["identifier"],
            text="",
            provider="opportunity_offer",
            # Fresh mail (no threading headers) — an offer is not a reply.
            subject=_OFFER_EMAIL_SUBJECT if channel == Channel.EMAIL else None,
            correlation_id=draft_id,
        )
        delivery = delivery_service.send(outbound_message, text)
        offer_metadata = {"source": "opportunity_offer", "draft_id": draft_id, "actor": actor}
        # The product (captured at approve time) lets the conversation view group
        # this offer under its own theme instead of the unrelated preceding query.
        if draft.get("offer_product"):
            offer_metadata["product"] = draft["offer_product"]
        turn = repository.append_turn(
            conversation_id=draft["conversation_id"],
            customer_id=draft["customer_id"],
            channel=identity["channel"],
            direction="outbound",
            text=text,
            ticket_id=None,
            delivery_status=delivery.get("status", "sent"),
            metadata=offer_metadata,
        )
        deliveries.append({"channel": identity["channel"],
                           "identifier": identity["identifier"],
                           "status": delivery.get("status", "sent")})
        turn_ids.append(turn["turn_id"])

    updated = repository.update_reply_draft(draft_id, status="sent", actor=actor, sent_text=text)
    repository.add_audit_event(
        "offer_draft_sent",
        draft_id,
        customer_id=draft.get("customer_id"),
        conversation_id=draft.get("conversation_id"),
        details={"actor": actor, "deliveries": deliveries,
                 "edited": text != (draft.get("draft_text") or "")},
    )
    return {"draft": updated, "turn_ids": turn_ids, "deliveries": deliveries}


@router.post("/{draft_id}/discard")
def discard_draft(draft_id: str, payload: DiscardDraftRequest) -> dict:
    repository = get_repository()
    draft = repository.get_reply_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Draft already {draft['status']}")
    updated = repository.update_reply_draft(draft_id, status="discarded", actor=payload.actor)
    repository.add_audit_event(
        "reply_draft_discarded",
        draft_id,
        customer_id=draft.get("customer_id"),
        conversation_id=draft.get("conversation_id"),
        ticket_id=draft.get("ticket_id"),
        details={"actor": payload.actor},
    )
    return updated
