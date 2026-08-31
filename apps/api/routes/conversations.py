import json
import logging

from fastapi import APIRouter, Depends, HTTPException

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_key
from services.neo4j_service.queries import TRANSACTIONAL_INTENTS
from services.orchestration_service.graph import HOLDING_MESSAGE
from services.rag_service.groq_generator import GroqGenerator

logger = logging.getLogger(__name__)

# Matches the customer-facing holding text the review gate sends in place of the AI reply.
HOLDING_PREFIX = HOLDING_MESSAGE.strip().lower()[:40]

router = APIRouter(prefix="/admin/conversations", tags=["admin"], dependencies=[Depends(require_admin_key)])

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


@router.get("/{conversation_id}/case-summary")
def case_summary(conversation_id: str, refresh: bool = False) -> dict:
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

    if not refresh:
        cached = repo.get_case_summary(conversation_id)
        if cached and cached.get("latest_turn_id") == latest_turn_id:
            return {
                "conversation_id": conversation_id,
                "status": "cached",
                "generated_at": cached.get("created_at"),
                "summary": {"situation": cached.get("situation", "")},
            }

    # Open tickets read from SQLite, the system of record for ticket status — the same
    # source the right-panel Open Tickets card uses, so the summary can never disagree
    # with the card sitting beside it.
    open_cases = []
    try:
        open_cases = repo.find_open_tickets_for_customer(conversation["customer_id"], limit=5) or []
    except Exception:
        logger.exception("case_summary_open_tickets_failed")

    generator = GroqGenerator()
    summary = generator.summarize_case(
        turns,
        {"open_cases": open_cases, "graph_context": {"name": conversation.get("display_name")}},
    )
    if summary is None:
        # No LLM (quota, outage, no key). Say so rather than showing the agent a
        # fabricated or stale-but-unlabelled summary.
        return {"conversation_id": conversation_id, "status": "unavailable", "summary": None}

    try:
        repo.save_case_summary(conversation_id, latest_turn_id, summary)
    except Exception:
        logger.exception("case_summary_save_failed")  # serve it anyway; caching is best-effort

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
