import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_auth
# The ticket side-effects of a reply live with the draft path and are REUSED here rather
# than reimplemented - see the note on send_agent_reply below.
from apps.api.routes.reply_drafts import _mark_ticket_responded
from services.channel_service.delivery import OutboundDeliveryService
from services.neo4j_service.queries import TRANSACTIONAL_INTENTS
from services.orchestration_service.graph import HOLDING_MESSAGE
from shared.schemas.messages import Channel, InboundMessage

logger = logging.getLogger(__name__)

# Matches the customer-facing holding text the review gate sends in place of the AI reply.
HOLDING_PREFIX = HOLDING_MESSAGE.strip().lower()[:40]

router = APIRouter(prefix="/admin/conversations", tags=["admin"], dependencies=[Depends(require_admin_auth)])

# Which graph node types an intent reads. Mirrors the branches in
# services/neo4j_service/queries.py::neo4j_answer — that function fetches EVERY record of
# the relevant type for the intent (it doesn't pick one), so naming the types is an
# accurate statement of what was read, not an approximation of it.
INTENT_GRAPH_TYPES = {
    "loan_status": ["Loan"],
    "loan_default_notice": ["Loan"],
    "claim_status": ["Claim"],
    "policy_status": ["Policy", "Claim"],
    "card_management": ["CreditCard"],
    "account_balance_inquiry": ["Account", "FixedDeposit"],
    "transaction_dispute": ["Transaction"],
}


class AgentReplyRequest(BaseModel):
    text: str
    actor: str = "admin"


@router.post("/{conversation_id}/reply")
def send_agent_reply(conversation_id: str, payload: AgentReplyRequest) -> dict:
    """Send an agent-composed reply on a conversation that has no pending AI draft.

    Before this, the composer under every conversation was a decoration: doSend() showed a
    "simulation mode" toast, cleared the box and called nothing. The ONLY way to reply was
    to send a held AI draft, so once that draft was sent the agent could never write to the
    customer again - which is the case for every answered ticket on the board, including
    the fraud case whose reply promised a follow-up nobody could then deliver.

    Deliberately NOT a second delivery path. It resolves the destination, then hands off to
    exactly what send_draft uses: OutboundDeliveryService().send(), append_turn(), and
    _mark_ticket_responded() - so the first-response clock, the logged/open -> in_progress
    transition and the promise clock behave identically however the reply was written.
    """
    repository = get_repository()
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Reply text is required")

    # A pending draft IS the reply surface - the UI hides the composer while one exists.
    # If one is somehow open, refuse rather than send alongside it: the customer would get
    # two messages and the draft would sit pending forever, exactly the drift send_draft
    # already guards against with its own 409.
    pending = repository.list_reply_drafts(conversation_id=conversation_id, status="pending")
    if pending:
        raise HTTPException(
            status_code=409,
            detail="A reply is held for review on this conversation — send or discard it instead.")

    # Channel comes from the LAST INBOUND turn, never from the customer's identity list.
    # Measured trap: this customer's `web_chat` identity is stored as their email address
    # and their `email` identity is the SAME address, so choosing a destination by identity
    # would put a real email in a real inbox for a web-chat conversation.
    turns = repository.list_conversation_turns(conversation_id)
    inbound = [t for t in turns if t.get("direction") == "inbound"]
    if not inbound:
        raise HTTPException(status_code=400, detail="Nothing inbound on this conversation to reply to")
    last_inbound = inbound[-1]

    try:
        channel = Channel(last_inbound.get("channel") or "")
    except ValueError:
        channel = Channel.WEB_CHAT

    # Web chat has no push provider - the customer reads the persisted turn on the portal's
    # next poll - so the identifier is unused there. For email/whatsapp it must be a real
    # destination, and the channel_identities row for THAT channel is the only source.
    identifier = ""
    if channel is not Channel.WEB_CHAT:
        identities = repository.list_customer_identifiers(conversation.get("customer_id") or "")
        match = next((i for i in identities if i.get("channel") == channel.value), None)
        if not match:
            raise HTTPException(
                status_code=400,
                detail=f"No {channel.value} address on record for this customer.")
        identifier = match["identifier"]

    # Threading: carry the original inbound mail's real Message-ID and subject so the reply
    # lands in the same Gmail thread rather than as a separate message.
    outbound_message = InboundMessage(
        channel=channel,
        channel_identifier=identifier,
        text="",
        provider="agent_composed_reply",
        subject=last_inbound.get("subject"),
        correlation_id=conversation_id,
        external_message_id=last_inbound.get("external_message_id"),
    )
    delivery = OutboundDeliveryService().send(outbound_message, text)

    ticket_id = last_inbound.get("ticket_id")
    turn = repository.append_turn(
        conversation_id=conversation_id,
        customer_id=conversation.get("customer_id"),
        channel=channel.value,
        direction="outbound",
        text=text,
        ticket_id=ticket_id,
        delivery_status=delivery.get("status", "sent"),
        metadata={"source": "agent_composed_reply", "actor": payload.actor},
    )

    # Same ticket side-effects as a draft send - one implementation, two callers. The turn
    # id anchors the promise (020): a reply that promises again restarts the follow-up loop
    # from HERE rather than from the first response.
    _mark_ticket_responded(repository, ticket_id, text, payload.actor,
                           turn_id=turn["turn_id"])

    repository.add_audit_event(
        "agent_reply_sent",
        turn["turn_id"],
        customer_id=conversation.get("customer_id"),
        conversation_id=conversation_id,
        ticket_id=ticket_id,
        details={"actor": payload.actor,
                 "delivery_status": delivery.get("status"),
                 "delivery_mode": delivery.get("delivery_mode"),
                 "channel": channel.value},
    )
    return {"turn_id": turn["turn_id"], "delivery": delivery, "ticket_id": ticket_id}


@router.get("/{conversation_id}/case-summary")
def case_summary(conversation_id: str, refresh: bool = False, ticket_id: str | None = None) -> dict:
    """An agent-facing summary of where this conversation stands.

    Generated on demand rather than per message. An agent reads a summary when they
    open a conversation, not once per inbound turn, so generating on write would spend
    a Groq call on every message for something usually never read. The cache is keyed
    to the newest turn: unchanged conversation → cached row, new turn → regenerate.
    Cost therefore tracks agent attention, not message volume.
    """
    repo = get_repository()
    conversation = repo.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    turns = repo.list_conversation_turns(conversation_id) or []
    if not turns:
        return {"conversation_id": conversation_id, "status": "empty", "summary": None}
    latest_turn_id = turns[-1]["turn_id"]

    # NO conversation-keyed cache here any more, and its absence is the point. This route
    # used to short-circuit on case_summaries, which holds ONE row per conversation: with
    # per-case summaries that returned the same text for every ticket on the conversation,
    # and it returned BEFORE the call below ever ran - so the rewiring underneath it was
    # dead code and both cases rendered the fraud dispute's summary.
    #
    # Caching now lives in case_review, keyed by ticket_id, which is the only key that can
    # tell two of a customer's cases apart.
    #
    # `open_cases` went with it: case_review assembles its own context from the case's own
    # turns, ticket and records, so the lookup fed nothing.

    # The situation comes from the SAME per-case review that produces Suggested Actions and
    # Suggested Offers - one LLM call behind all three cards instead of three that each
    # re-sent this case. Scoped to the case as well as merged: the old call was handed the
    # whole conversation, which on the live customer is 30 turns across 8 tickets, and it
    # needed a redaction hack because our own quoted status emails let a since-resolved
    # ticket id outnumber the authoritative block 4:1. A single case carries none of that.
    # ticket_id names WHICH case to summarise, so the card matches the one the Detailed
    # view is showing. Absent, the route falls back to the conversation's active case,
    # which is what it did before the cards became per-case.
    from apps.api.routes.agent_assist import case_review
    review = case_review(repo, conversation_id, ticket_id, refresh=refresh)
    summary = None
    if not review.get("llm_error") and not review.get("suppressed") and review.get("situation"):
        summary = {"situation": review["situation"], "model": None}
    if summary is None:
        # No LLM (quota, outage, no key). Say so rather than showing the agent a
        # fabricated or stale-but-unlabelled summary.
        return {"conversation_id": conversation_id, "status": "unavailable", "summary": None}

    # Nothing is written here. case_review already stored this review against its TICKET;
    # writing it again to case_summaries would file a per-case situation under a
    # conversation-wide key, which is the exact confusion that made every case on this
    # conversation report the fraud dispute's summary.

    return {
        "conversation_id": conversation_id,
        "status": "generated",
        "model": summary.get("model"),
        "summary": {"situation": summary.get("situation", "")},
    }


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    conversation = get_repository().get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("")
def list_conversations() -> list[dict]:
    return get_repository().list_conversations()


@router.get("/turns/{turn_id}/provenance")
def turn_provenance(turn_id: str) -> dict:
    """Where a reply's information came from: the customer graph, the knowledge base, or neither.

    Answers are produced from one of two sources, and which one is a per-message fact, not a
    property of the system: transactional intents read the customer's own records from Neo4j,
    everything else retrieves passages from the KB. This reports the actual source for one
    reply so the UI can show it rather than implying every answer came from the graph.
    """
    repo = get_repository()
    turn = repo.get_turn(turn_id)
    if turn is None:
        raise HTTPException(status_code=404, detail="Turn not found")

    # A holding message is not an answer — the real reply is still a pending draft. Any
    # retrieval recorded against it belongs to a reply the customer never received, so
    # reporting it as "where this answer came from" would be describing the wrong text.
    if (turn.get("text") or "").strip().lower().startswith(HOLDING_PREFIX):
        return {
            "turn_id": turn_id, "intent": turn.get("intent"), "retrieval_backend": None,
            "source": "holding", "graph_types": [], "account_context": False, "citations": [],
        }

    evidence = repo.list_retrieval_evidence(turn_id) or []
    # The repository returns the column as a PARSED dict under "metadata" — not the raw
    # "metadata_json" string the table stores. Reading the column name yields None.
    backend = None
    for ev in evidence:
        meta = ev.get("metadata")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (ValueError, TypeError):
                meta = {}
        backend = (meta or {}).get("retrieval") or backend

    # Which intent produced this reply. An outbound turn's own intent is unreliable here —
    # it can be a system label like "customer_not_registered" that says nothing about what
    # was retrieved — so always prefer the inbound message this reply answers.
    intent = _triggering_intent(repo, turn) or turn.get("intent")
    graph_types = INTENT_GRAPH_TYPES.get(intent or "", [])
    # The recorded backend is the ground truth when we have it: a transactional intent can
    # still fall through to the KB when the customer has no such record (neo4j_answer
    # returns None and RAG answers instead), so intent alone would over-claim.
    if backend:
        graph_backed = backend == "neo4j_graph"
    else:
        graph_backed = bool(graph_types) and (intent in TRANSACTIONAL_INTENTS)
    if not graph_backed:
        graph_types = []

    # SECOND PATH — the one that made an earlier version of this endpoint lie. Retrieval is
    # not the only way customer data reaches the model: graph.py loads `graph_context` for
    # EVERY message and the generator renders it into a trusted "Customer account context"
    # slot, independent of retrieval. So a misclassified question ("when is my FD maturity
    # date?" → general_inquiry) can answer from real account data while retrieval fetched
    # something unrelated. Reporting only the retrieval path claimed "no account records
    # were read" on exactly those replies. We cannot replay the prompt, but we CAN say
    # whether this customer has records of the kind the answer mentions.
    account_context = _account_context_available(repo, turn)

    # Is this reply part of an ongoing case, and which messages make up that case?
    # Provenance answered only "graph or knowledge base" — a per-message fact — and could
    # never show that a reply CONTINUES something. A follow-up on an open ticket rendered
    # exactly like the first message of a brand-new one.
    case = _case_for_turn(repo, turn)

    return {
        "turn_id": turn_id,
        "intent": intent,
        "retrieval_backend": backend,
        # The ticket this reply belongs to, plus every message on it (oldest first) when
        # there is more than one — i.e. only when there is real continuity to show.
        "case": case,
        # "graph" → retrieval read this customer's records from Neo4j; "ticket" → their own
        # support record was read from SQLite; "kb" → passages were retrieved; "none" → no
        # retrieval ran (a holding message, an offer, a canned reply).
        # "ticket" is its own state rather than folded into either neighbour: it is not a
        # graph read (the data is SQLite, so claiming "graph" would over-claim exactly the way
        # Fix 65 set out to stop), and it is not a similarity search, so the KB block's
        # "closest matches / always returns a nearest match" caveats describe a mechanism that
        # never ran. An exact record read at 0.98 is a third thing.
        "source": (
            "graph" if graph_backed
            else "ticket" if backend == "customer_ticket_lookup"
            else "kb" if evidence
            else "none"
        ),
        "graph_types": graph_types,
        # True when this customer has BFSI records, which are placed in the model's trusted
        # account-context slot on every message regardless of retrieval. The UI must not
        # claim "no account data was used" while this is true.
        "account_context": account_context,
        "citations": [
            {
                "source": ev.get("source"),
                "score": ev.get("score"),
                "text": (ev.get("chunk_text") or "")[:400],
            }
            for ev in evidence
        ],
    }


def _case_for_turn(repo, turn: dict) -> dict | None:
    """The ticket this reply belongs to and the customer messages on it, oldest first.

    Read from SQLite rather than the graph: it is the system of record for ticket
    attachment (the matching tiers all run against it), so it cannot drift out of sync
    with what the conversation view shows.

    Returns None when the reply has no ticket, or when the ticket has only one customer
    message — a single message is not continuity, and claiming it is would overstate.
    """
    ticket_id = turn.get("ticket_id")
    if not ticket_id:
        return None
    ticket = repo.get_ticket(ticket_id) or {}
    # Only OUTBOUND turns carry ticket_id; the customer's own message does not. So walk the
    # conversation in order and attribute each inbound message to the ticket of the reply
    # that follows it — the same pairing the conversation view uses.
    turns = repo.list_conversation_turns(turn.get("conversation_id") or "")
    messages, pending = [], None
    for t in turns:
        if t.get("direction") == "inbound":
            pending = t
            continue
        if pending is not None and t.get("ticket_id") == ticket_id:
            messages.append({
                "turn_id": pending.get("turn_id"),
                "text": (pending.get("text") or "")[:200],
                "channel": pending.get("channel"),
                "created_at": pending.get("created_at"),
                # Marks the exchange the agent clicked, so the panel can show where this
                # reply sits within the case rather than just listing it.
                "is_this_turn": t.get("turn_id") == turn.get("turn_id"),
            })
            pending = None
    if len(messages) < 2:
        return None
    scope = (ticket.get("metadata") or {}).get("ticket_scope") or ""
    return {
        "ticket_id": ticket_id,
        "status": ticket.get("status"),
        "intent": ticket.get("intent"),
        # "transaction_dispute:imps" → "imps": the specific matter this case narrowed to.
        "scope": scope.split(":", 1)[1] if ":" in scope else "",
        "channels": sorted({m["channel"] for m in messages if m.get("channel")}),
        "messages": messages,
    }


def _account_context_available(repo, turn: dict) -> bool:
    """Whether this customer resolves to a real graph customer with records.

    graph.py hands that context to the generator on every message, so it is part of what
    the model saw even when retrieval went elsewhere.
    """
    try:
        from apps.api.routes.customers import _resolve_graph_customer
        _, customer = _resolve_graph_customer(turn.get("customer_id") or "")
        return bool(customer)
    except Exception:
        return False


def _triggering_intent(repo, turn: dict) -> str | None:
    """Intent of the inbound message this reply answers."""
    turns = repo.list_recent_turns(turn.get("conversation_id"), limit=200) or []
    turns.sort(key=lambda t: t.get("created_at") or "")
    idx = next((i for i, t in enumerate(turns) if t.get("turn_id") == turn.get("turn_id")), None)
    if idx is None:
        return None
    for prev in reversed(turns[:idx]):
        if prev.get("direction") == "inbound" and prev.get("intent"):
            return prev["intent"]
    return None
