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
