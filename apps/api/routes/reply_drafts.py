"""Admin routes for human-in-the-loop reply drafts.

When the review gate holds an AI reply (see services/workflow_service/review_gate.py), the
AI's answer is stored as a pending draft. An admin lists held drafts, edits the text, and
sends it manually — which delivers to the customer (WhatsApp/email push; web-chat via the
portal's history poll) and persists a normal outbound turn.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_key
from services.channel_service.delivery import OutboundDeliveryService
from shared.schemas.messages import Channel, InboundMessage

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

    updated = repository.update_reply_draft(
        draft_id, status="sent", actor=payload.actor, sent_text=text,
    )
    repository.add_audit_event(
        "reply_draft_sent",
        draft_id,
        customer_id=draft.get("customer_id"),
        conversation_id=draft.get("conversation_id"),
        ticket_id=draft.get("ticket_id"),
        details={"actor": payload.actor, "delivery_status": delivery.get("status"),
                 "edited": text != (draft.get("draft_text") or "")},
    )
    return {"draft": updated, "turn_id": turn["turn_id"], "delivery": delivery}


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
        turn = repository.append_turn(
            conversation_id=draft["conversation_id"],
            customer_id=draft["customer_id"],
            channel=identity["channel"],
            direction="outbound",
            text=text,
            ticket_id=None,
            delivery_status=delivery.get("status", "sent"),
            metadata={"source": "opportunity_offer", "draft_id": draft_id, "actor": actor},
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
