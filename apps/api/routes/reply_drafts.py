"""Admin routes for human-in-the-loop reply drafts.

When the review gate holds an AI reply (see services/workflow_service/review_gate.py), the
AI's answer is stored as a pending draft. An admin lists held drafts, edits the text, and
sends it manually — which delivers to the customer (WhatsApp/email push; web-chat via the
portal's history poll) and persists a normal outbound turn.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_auth
from services.channel_service.delivery import OutboundDeliveryService
from services.persistence_service.repository import utc_now
from shared.schemas.messages import Channel, InboundMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/reply-drafts", tags=["admin"], dependencies=[Depends(require_admin_auth)])


# Draft kinds that get a channel picker: an approved offer (proactive, fans out) and a
# draft the agent asked for by approving a Suggested Action. Keyed on provider because
# that is what already distinguishes them - see renderDraftCard in app.js.
_PICKER_PROVIDERS = {"nudge_reply", "follow_up_nudge"}


class SendDraftRequest(BaseModel):
    text: str            # final text the agent sends (may differ from the AI draft)
    actor: str = "admin"
    # Which of the customer's reachable channels the agent ticked. None means "decide as
    # before" - every push channel for an offer, the draft's own channel for a reply - so
    # an older caller that omits it is unchanged.
    channels: list[str] | None = None


class DiscardDraftRequest(BaseModel):
    actor: str = "admin"


@router.get("")
def list_drafts(conversation_id: str | None = None, status: str = "pending") -> list[dict]:
    # status="" (empty) returns all statuses
    repository = get_repository()
    drafts = repository.list_reply_drafts(
        conversation_id=conversation_id, status=status or None,
    )
    # Where this customer can be reached, so the card can offer the agent a choice rather
    # than deciding for them. Only for the two draft kinds that fan out or are proactive -
    # an offer, and a draft the agent asked for by approving a Suggested Action. A held
    # pipeline reply answers a question that arrived on one channel and belongs on that
    # channel, so it is not given a picker and pays for no lookup.
    for draft in drafts:
        if draft.get("channel") == "offer" or draft.get("provider") in _PICKER_PROVIDERS:
            draft["reachable_channels"] = reachable_push_identities(
                repository, draft.get("customer_id") or "")
    return drafts


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
        return _send_offer_draft(repository, draft, draft_id, text, payload.actor,
                                 channels=payload.channels)

    # An approved nudge or follow-up the agent chose to send somewhere OTHER than the
    # channel the draft was built for - or to more than one - goes through the same fan-out
    # the offer path uses. It is the only code that delivers one text to several
    # destinations, and duplicating it here would be a second copy to keep in step.
    #
    # Deliberately not used for the single-channel case below: that path threads the reply
    # onto the original inbound turn (In-Reply-To / "Re: <subject>"), which is meaningful
    # only on the channel the question arrived on. Sending the same text to a second
    # channel is a fresh message, not a threaded reply.
    if payload.channels is not None:
        wanted = {str(c).strip().lower() for c in payload.channels}
        if wanted and wanted != {str(draft.get("channel") or "").lower()}:
            return _send_offer_draft(repository, draft, draft_id, text, payload.actor,
                                     channels=payload.channels)

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

    # Close the human-in-the-loop loop on the TICKET. Measured before this existed: all
    # four sent drafts on the live database left their tickets untouched and still 'open',
    # two of them critical L3 - a person had read the case, written the reply and sent it,
    # and the ticket recorded none of it. The response SLA therefore ran forever and every
    # answered case kept reporting as breached.
    # `text` is passed explicitly, NOT read from `draft`: draft was loaded before the send
    # and its sent_text is still None at this point, so reading it there would silently
    # disable promise detection - the check would run on an empty string every time.
    _mark_ticket_responded(repository, draft.get("ticket_id"), text, payload.actor,
                           turn_id=turn["turn_id"])

    repository.add_audit_event(
        "reply_draft_sent",
        draft_id,
        customer_id=draft.get("customer_id"),
        conversation_id=draft.get("conversation_id"),
        ticket_id=draft.get("ticket_id"),
        # delivery_mode in the PERMANENT record too, not just the toast: "delivery_status
        # sent" in an audit row is the same three-way ambiguity, read back later by someone
        # with no container log to check it against.
        details={"actor": payload.actor, "delivery_status": delivery.get("status"),
                 "delivery_mode": delivery.get("delivery_mode"),
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


# Phrases that COMMIT us to coming back to the customer. Measured against the live fraud
# reply, which said "is currently under investigation", "will update you on the status
# shortly" and "will follow up with you" - four promises, none of them tracked anywhere.
#
# Deliberately a small, literal list rather than an LLM call: this runs on every sent
# reply, requests are the binding Groq limit, and a missed promise costs a follow-up
# reminder we did not schedule - not a wrong answer to a customer. A false positive is
# cheap too (a follow-up flag a human clears).
_PROMISE_PHRASES = (
    "will update you",
    "will get back to you",
    "will follow up",
    "will contact you",
    "will reach out",
    "under investigation",
    "is being reviewed",
    "is reviewing",
    "we will inform you",
    "keep you posted",
    "keep you updated",
)

# How long before an unkept promise starts showing on the board. Deliberately not tied to
# the priority SLA: that clock measured our FIRST response, this one measures a commitment
# made after it, and a promise made on a low-priority case is no less of a promise.
_FOLLOW_UP_HOURS = 24


def _promised_follow_up(text: str) -> bool:
    lowered = (text or "").lower()
    return any(phrase in lowered for phrase in _PROMISE_PHRASES)


def _mark_ticket_responded(repository, ticket_id: str | None, sent_text: str, actor: str,
                           turn_id: str | None = None) -> None:
    """Record that a human answered, and whether the answer promised a follow-up.

    Takes a ticket_id, NOT a draft: an agent can also reply from the conversation composer,
    where no draft row exists (see apps/api/routes/conversations.py). Both send paths must
    apply the same rules - first-response clock, logged/open -> in_progress, and the
    promise clock - or the two would drift and one would forget something.

    `turn_id` is the outbound turn this reply just created, and it becomes the ANCHOR for
    the promise (migration 020). Every reply re-decides the promise state:

      * it promises      -> new deadline, anchor moves to THIS turn, so the nudge asks
                            "anything since here?" and the loop continues for as long as
                            the case does.
      * it promises not  -> BOTH fields cleared. The promise was answered and nothing new
                            was undertaken. Without this the board kept counting down
                            "due in 13h" after a reply that said the dispute was resolved.

    Best-effort by design: the customer already has the reply by the time this runs, so a
    failure here must never surface as a failed send. It is wrapped rather than allowed to
    raise for that reason alone.
    """
    if not ticket_id:
        return
    try:
        ticket = repository.get_ticket(ticket_id)
        if not ticket:
            return

        updates = {}
        # FIRST response only - never overwrite it. The field answers "when did we first
        # reply", so a second reply on the same ticket must not reset the clock and make a
        # late first answer look punctual.
        if not ticket.get("first_response_at"):
            updates["first_response_at"] = utc_now()

        if _promised_follow_up(sent_text):
            updates["follow_up_due_at"] = (
                datetime.now(timezone.utc) + timedelta(hours=_FOLLOW_UP_HOURS)
            ).isoformat()
            updates["follow_up_turn_id"] = turn_id
        elif ticket.get("follow_up_due_at"):
            # A promise was outstanding and this reply did not renew it - so it was kept.
            # Cleared rather than left to expire, because an expired clock reads as a
            # BROKEN promise on the board and in analytics.
            updates["follow_up_due_at"] = None
            updates["follow_up_turn_id"] = None

        # A logging ticket that a human has now answered is real work, so it stops being a
        # grouping id. open -> in_progress records that someone is actually on it; the
        # value has existed in TicketStatus since the redesign and has never been written.
        if ticket.get("status") in ("logged", "open"):
            updates["status"] = "in_progress"

        if not updates:
            return
        repository.update_ticket(ticket_id, **updates)
        repository.add_ticket_event(ticket_id, "customer_responded", actor, updates)
    except Exception:
        logger.warning("ticket_response_marking_failed",
                       extra={"ticket_id": ticket_id}, exc_info=True)


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


def reachable_push_identities(repository, customer_id: str) -> list[dict]:
    """Where this customer can actually be reached: whatsapp/email, deduped.

    Combines two sources, in this order:

      1. the CUSTOMER RECORD in Neo4j - their email and phone as the bank holds them.
         This is the authority on where someone can be reached, and it was not being
         consulted at all.
      2. channel_identities - every address they have written in FROM, which catches a
         second email the record does not carry.

    channel_identities alone was the old source, and it answers a different question:
    "which channels has this customer used". A customer whose phone sits on their BFSI
    record but who has only ever used web chat had no whatsapp row, so the offer card
    promised "Delivers via WhatsApp + Email" and the send reached email only. Both seeded
    portal customers were in exactly that state.

    Record first so its address wins the dedupe; _push_dedupe_key collapses a number
    stored both bare and 91-prefixed to one destination.
    """
    identities: list[dict] = []
    try:
        if os.getenv("NEO4J_ENABLED", "true").lower() == "true":
            from services.neo4j_service.client import Neo4jClient
            from services.neo4j_service.queries import get_customer_by_id

            client = Neo4jClient()
            try:
                graph_id = ""
                for row in repository.list_customer_identifiers(customer_id) or []:
                    if row.get("channel") == "graph":
                        graph_id = row.get("identifier") or ""
                        break
                record = get_customer_by_id(client, graph_id) if graph_id else None
                if record:
                    if record.get("email"):
                        identities.append({"channel": "email", "identifier": str(record["email"]).strip()})
                    if record.get("phone"):
                        identities.append({"channel": "whatsapp", "identifier": str(record["phone"]).strip()})
            finally:
                client.close()
    except Exception:
        # The record is an enrichment, not a requirement: without Neo4j this falls back to
        # exactly the old behaviour rather than refusing to send.
        logger.warning("reachable_identities_graph_lookup_failed", exc_info=True)

    # All three destinations, always. Web chat is not a PUSH channel - delivery.py has no
    # outbound provider for it, so a message sent there waits in the portal until the
    # customer next looks - but it is still somewhere a reply can be sent, and the agent
    # decides whether that is appropriate.
    #
    # This used to be gated on an include_web_chat flag so the offer fan-out could exclude
    # it. That made ONE function answer "where can this customer be reached" differently
    # depending on who asked, which is a question with one answer. The choice belongs on
    # the card (see draftChannelPicker: an offer leaves web chat unticked), not buried in
    # channel resolution where nothing on screen explains it.
    identities.extend(
        i for i in (repository.list_customer_identifiers(customer_id) or [])
        if i.get("channel") in ("whatsapp", "email", "web_chat")
    )
    return _dedupe_push_identifiers(identities)


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


def _send_offer_draft(repository, draft: dict, draft_id: str, text: str, actor: str,
                      channels: list[str] | None = None) -> dict:
    """Deliver an approved offer to every push channel on record (whatsapp/email).

    A missing channel is skipped; at least one identifier is guaranteed because
    the approve endpoint refuses to create an offer draft without one.
    """
    # The customer RECORD as well as the channels they have written in from - see
    # reachable_push_identities. Reading channel_identities alone meant a customer whose
    # phone is on their BFSI record but who has only ever used web chat had no whatsapp
    # row, so this fan-out silently delivered to email while the card promised both.
    wanted = {str(c).strip().lower() for c in channels} if channels is not None else set()
    push = reachable_push_identities(repository, draft.get("customer_id") or "")
    # Narrow to what the agent ticked. Filtering rather than trusting the list means a
    # channel the customer is not reachable on cannot be sent to by editing the request.
    if channels is not None:
        push = [i for i in push if i.get("channel") in wanted]
        if not push:
            raise HTTPException(
                status_code=400,
                detail="Select at least one channel this customer can be reached on.")
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
        # delivery_mode, not just status: an offer that only reached the container log
        # reports status "sent" exactly like one a provider accepted. Carried per channel
        # because an offer fans out to WhatsApp AND email - one can be delivered while the
        # other is logged_only, and a single summary status would hide that.
        deliveries.append({"channel": identity["channel"],
                           "identifier": identity["identifier"],
                           "status": delivery.get("status", "sent"),
                           "delivery_mode": delivery.get("delivery_mode")})
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

    # Discarding a draft that came from an APPROVED recommendation puts it back on the card.
    #
    # Approving a Suggested Action or Offer does two things: flips the recommendation to
    # `approved` and writes this draft. Discarding undid only the second, so the
    # recommendation stayed `approved` and the card stopped offering it although nothing
    # was sent and the agent never pressed Dismiss.
    #
    # THE GUARD IS THE POINT. The card holds ONE pending row per (ticket, action_type) -
    # the same rule get_next_best_actions applies with `existing_by_type`. Approving causes
    # a re-render, that review finds no pending row of this type (this one is `approved`)
    # and writes a REPLACEMENT. Reopening blindly then leaves two identical cards on
    # screen. Reopening without checking is what produced four identical "Customer upset"
    # nudges on the live conversation.
    #
    # So: reopen only when nothing has taken this row's place. If something has, the
    # suggestion is already back on the card under a different id and there is nothing to do.
    rec_id = draft.get("recommendation_id")
    if rec_id:
        rec = repository.get_agent_assist_recommendation(rec_id)
        # Only an `approved` row is reopened. A dismissed one was a decision about the
        # SUGGESTION and stays dismissed; this undoes the approve that made this draft.
        if rec and rec.get("status") == "approved":
            replacement = [
                row for row in repository.list_agent_assist_recommendations(
                    conversation_id=rec.get("conversation_id"), status="pending")
                if row.get("action_type") == rec.get("action_type")
                and row.get("ticket_id") == rec.get("ticket_id")
            ]
            if not replacement:
                repository.update_agent_assist_recommendation(
                    rec_id, status="pending", actor=payload.actor)
                repository.add_audit_event(
                    "nba_recommendation_reopened",
                    rec_id,
                    customer_id=draft.get("customer_id"),
                    conversation_id=draft.get("conversation_id"),
                    ticket_id=draft.get("ticket_id"),
                    details={"actor": payload.actor, "via": "draft_discarded",
                             "draft_id": draft_id},
                )

    repository.add_audit_event(
        "reply_draft_discarded",
        draft_id,
        customer_id=draft.get("customer_id"),
        conversation_id=draft.get("conversation_id"),
        ticket_id=draft.get("ticket_id"),
        details={"actor": payload.actor},
    )
    return updated
