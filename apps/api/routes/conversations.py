import json

from fastapi import APIRouter, Depends, HTTPException

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_key
from services.neo4j_service.queries import TRANSACTIONAL_INTENTS
from services.orchestration_service.graph import HOLDING_MESSAGE

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

    return {
        "turn_id": turn_id,
        "intent": intent,
        "retrieval_backend": backend,
        # "graph" → retrieval read this customer's records; "kb" → passages were retrieved;
        # "none" → no retrieval ran (a holding message, an offer, a canned reply).
        "source": "graph" if graph_backed else ("kb" if evidence else "none"),
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
