import hashlib
import hmac
import logging
import os
import re
import time
from datetime import datetime

import jwt
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from apps.api.dependencies.runtime import get_repository, get_router
from services.channel_service.adapters.web_chat_adapter import WebChatAdapter
from shared.schemas.messages import EmailWebhookPayload, WebChatWebhookPayload, WhatsAppWebhookPayload
from shared.utils.ids import new_id

from .webhooks import handle_email_message, handle_whatsapp_message

router = APIRouter(prefix="/user", tags=["user-portal"])
logger = logging.getLogger(__name__)

_TOKEN_TTL_SECONDS = 28800


class UserLoginRequest(BaseModel):
    user_id: str
    password: str


class UserSignupRequest(BaseModel):
    user_id: str
    email: str
    password: str


class UserMessageRequest(BaseModel):
    channel: str
    message: str = Field(min_length=1, max_length=5000)
    contact_identifier: str | None = Field(default=None, max_length=320)


class UserChatMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


def _make_token(user_id: str) -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="JWT_SECRET is not configured")
    return jwt.encode(
        {
            "sub": user_id,
            "role": "user_portal",
            "exp": int(time.time()) + _TOKEN_TTL_SECONDS,
        },
        secret,
        algorithm="HS256",
    )


def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}:{hashed}"


def _verify_password(password: str, stored: str) -> bool:
    parts = stored.split(":", 1)
    if len(parts) != 2:
        return False
    salt, expected = parts
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return hmac.compare_digest(actual, expected)


def _require_user(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="User login required")
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="JWT_SECRET is not configured")
    try:
        payload = jwt.decode(authorization[7:], secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired user session") from exc
    if payload.get("role") != "user_portal" or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid user session")
    return str(payload["sub"])


def _portal_email(user_id: str) -> str:
    if "@" in user_id:
        return user_id.strip().lower()
    local = re.sub(r"[^a-z0-9._-]+", ".", user_id.lower()).strip(".") or "customer"
    return f"{local}@portal.demo"


def _portal_phone(user_id: str) -> str:
    digits = str(int(hashlib.sha256(user_id.encode()).hexdigest()[:12], 16))[-10:].zfill(10)
    return "91" + digits


def _graph_customer_id(user_id: str) -> str:
    digits = str(int(hashlib.sha256(user_id.encode()).hexdigest()[:12], 16))[-6:].zfill(6)
    return "CUST" + digits


def _resolve_graph_customer_id(user_id: str, email: str = "", phone: str = "") -> str:
    """Return the graph customer_id to use in message metadata.

    Prefers an EXISTING BFSI customer matched by email/phone (so account queries
    find real loans/cards/FD). Falls back to the deterministic hash id for
    brand-new portal users who aren't in the BFSI dataset. Deterministic for a
    given (email/phone), so the GET history path and the POST send path always
    resolve to the SAME customer_id — avoiding split conversations.
    """
    if os.getenv("NEO4J_ENABLED", "true").lower() == "true":
        client = None
        try:
            from services.neo4j_service.client import Neo4jClient
            from services.neo4j_service.queries import get_customer_by_identifier

            client = Neo4jClient()
            for candidate in (email, phone):
                if candidate:
                    existing = get_customer_by_identifier(client, candidate)
                    if existing and existing.get("customer_id"):
                        return str(existing["customer_id"])
        except Exception:
            logger.warning("portal_resolve_graph_customer_id_failed", extra={"user_id": user_id}, exc_info=True)
        finally:
            if client is not None:
                client.close()
    return _graph_customer_id(user_id)


def _xlsx_date_today() -> str:
    today = datetime.now()
    return f"{today.month}/{today.day}/{str(today.year)[-2:]}"


def _upsert_customer_graph_user(user_id: str, email: str, phone: str = "", channel: str = "portal") -> dict:
    if os.getenv("NEO4J_ENABLED", "true").lower() != "true":
        return {"enabled": False, "customer_id": _graph_customer_id(user_id)}
    client = None
    try:
        from services.neo4j_service.client import Neo4jClient
        from services.neo4j_service.queries import get_customer_by_identifier
        from services.neo4j_service.writer import upsert_customer

        client = Neo4jClient()
        today = _xlsx_date_today()

        # Match an EXISTING BFSI customer (loaded from the dataset) by email/phone
        # before minting a synthetic hash-based id. Otherwise the portal creates a
        # phantom Customer node with no loans/cards/FD, and account-specific queries
        # falsely escalate ("no details found") even though the real customer has data.
        existing = None
        for candidate in (email, phone):
            if candidate:
                existing = get_customer_by_identifier(client, candidate)
                if existing:
                    break

        if existing and existing.get("customer_id"):
            graph_customer_id = str(existing["customer_id"])
            # Refresh only runtime fields; do NOT seed synthetic records over the
            # real customer's existing BFSI data.
            upsert_customer(
                client,
                customer_id=graph_customer_id,
                phone=phone,
                email=email,
                secondary_email="",
                city="",
                country="India",
                registration_date="",
                last_activity_date=today,
                name=existing.get("name") or user_id,
                channel=channel,
            )
            return {
                "enabled": True,
                "status": "matched_existing",
                "customer_id": graph_customer_id,
            }

        # No existing BFSI customer matched this email/phone. Do NOT fabricate a
        # customer node or synthetic loans/cards/FD — that would make an unknown user
        # look "registered" (with fake data) and bypass CustomerValidationAgent's
        # reject-unregistered flow. Leaving no node means account-specific intents are
        # correctly routed to _reject_unregistered_customer; general FAQs still work.
        return {
            "enabled": True,
            "status": "unregistered",
            "customer_id": _graph_customer_id(user_id),
        }
    except Exception as exc:
        logger.warning("portal_customer_graph_upsert_failed", extra={"user_id": user_id}, exc_info=True)
        return {"enabled": True, "status": "failed", "error": str(exc), "customer_id": _graph_customer_id(user_id)}
    finally:
        if client is not None:
            client.close()


def _owns_conversation(conversation: dict, user_id: str) -> bool:
    return any(
        turn.get("metadata", {}).get("portal_user_id") == user_id
        for turn in conversation.get("turns", [])
    )


# Interim acknowledgement injected before a human-reviewed reply (mirrors
# HOLDING_MESSAGE in services/orchestration_service/graph.py). Detected so it can
# be shown as a demoted "auto-ack" line rather than the substantive answer.
_HOLDING_MARKER = "will help you with this shortly"


def _build_ticket_exchanges(turns: list[dict], ticket_id: str) -> list[dict]:
    """Reconstruct a ticket's full exchange history from a conversation's turns.

    In this data only OUTBOUND turns carry ``ticket_id``; the customer's inbound
    turns have none. An inbound belongs to ``ticket_id`` when the next outbound
    carries that ticket. Each customer message plus the reply(ies) that follow it
    (until the next customer message) becomes one exchange:
    ``{message, holding, response, created_at}``. ``turns`` must be chronological.
    """
    n = len(turns)
    belongs = [False] * n
    for i, turn in enumerate(turns):
        if turn.get("direction") == "outbound":
            belongs[i] = turn.get("ticket_id") == ticket_id
        elif turn.get("direction") == "inbound":
            for j in range(i + 1, n):
                if turns[j].get("direction") == "outbound":
                    belongs[i] = turns[j].get("ticket_id") == ticket_id
                    break

    exchanges: list[dict] = []
    current: dict | None = None
    for i, turn in enumerate(turns):
        if not belongs[i]:
            if turn.get("direction") == "inbound":
                current = None  # a non-ticket customer message ends the ticket run
            continue
        text = turn.get("text") or ""
        if turn.get("direction") == "inbound":
            current = {"message": text, "holding": None, "response": None,
                       "created_at": turn.get("created_at")}
            exchanges.append(current)
        else:  # outbound belonging to this ticket
            if current is None:
                current = {"message": None, "holding": None, "response": None,
                           "created_at": turn.get("created_at")}
                exchanges.append(current)
            if _HOLDING_MARKER in text:
                current["holding"] = text
            else:
                current["response"] = text
            current["created_at"] = turn.get("created_at")
    return exchanges


def _ticket_view(conversation: dict, tickets: list[dict]) -> dict:
    turns = conversation.get("turns", [])
    latest_response = next(
        (turn.get("text") for turn in reversed(turns) if turn.get("direction") == "outbound"),
        None,
    )
    latest_inbound = next(
        (turn for turn in reversed(turns) if turn.get("direction") == "inbound"),
        {},
    )
    conversation_tickets = [
        ticket for ticket in tickets if ticket.get("conversation_id") == conversation["conversation_id"]
    ]
    latest_ticket = conversation_tickets[0] if conversation_tickets else None
    return {
        "conversation_id": conversation["conversation_id"],
        "ticket_id": latest_ticket.get("ticket_id") if latest_ticket else latest_inbound.get("ticket_id"),
        "status": latest_ticket.get("status") if latest_ticket else conversation.get("status", "active"),
        "channel": latest_inbound.get("channel"),
        "contact_identifier": latest_inbound.get("metadata", {}).get("portal_contact_identifier"),
        "message": latest_inbound.get("text"),
        "latest_response": latest_response,
        "created_at": conversation.get("created_at"),
        "updated_at": conversation.get("updated_at"),
    }


@router.post("/auth/login")
def user_login(request: UserLoginRequest) -> dict:
    user_id = request.user_id.strip()
    if not user_id or not request.password:
        raise HTTPException(status_code=400, detail="User ID and password are required")
    user = get_repository().get_customer_user_by_id(user_id)
    if not user or not _verify_password(request.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid user ID or password")
    user_public = {key: value for key, value in user.items() if key != "password_hash"}
    return {
        "token": _make_token(user_id),
        "expires_in": _TOKEN_TTL_SECONDS,
        "user": {**user_public, "role": "customer"},
    }


@router.post("/auth/signup")
def user_signup(request: UserSignupRequest) -> dict:
    user_id = request.user_id.strip()
    email = request.email.strip().lower()
    if len(user_id) < 3:
        raise HTTPException(status_code=400, detail="User ID must be at least 3 characters")
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    repo = get_repository()
    if repo.get_customer_user_by_id(user_id):
        raise HTTPException(status_code=409, detail="User ID already exists")
    if repo.get_customer_user_by_email(email):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = repo.create_customer_user(user_id, email, _hash_password(request.password))
    graph_status = _upsert_customer_graph_user(user_id, email)
    return {
        "token": _make_token(user_id),
        "expires_in": _TOKEN_TTL_SECONDS,
        "user": {**user, "role": "customer"},
        "graph": graph_status,
    }


@router.post("/messages")
def submit_user_message(
    request: UserMessageRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    user_id = _require_user(authorization)
    user = get_repository().get_customer_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user session")
    channel = request.channel.strip().lower()
    contact_identifier = (request.contact_identifier or "").strip()
    email = str(user.get("email") or _portal_email(user_id)).strip().lower()
    phone = _portal_phone(user_id)
    if channel == "email":
        email = contact_identifier.lower() or email
        if "@" not in email:
            raise HTTPException(status_code=400, detail="Enter a valid email address")
    elif channel == "whatsapp":
        phone = re.sub(r"\D", "", contact_identifier) or phone
        if len(phone) < 10 or len(phone) > 15:
            raise HTTPException(status_code=400, detail="Enter a valid WhatsApp number with country code")
    metadata = {
        "portal_user_id": user_id,
        "portal_graph_customer_id": _resolve_graph_customer_id(user_id, email, phone),
        "portal_contact_identifier": email if channel == "email" else phone,
        "source": "user_portal",
        "provider": "whatsapp_cloud" if channel == "whatsapp" else "email_user_portal",
        "linked_email": email,
        "linked_phone": phone,
    }
    if channel == "whatsapp":
        metadata["outbound_provider"] = "meta"
    graph_status = _upsert_customer_graph_user(user_id, email, phone, channel)
    if channel == "email":
        response = handle_email_message(
            EmailWebhookPayload(
                from_email=email,
                subject="Customer portal request",
                body=request.message.strip(),
                message_id=new_id("portal_email"),
                metadata=metadata,
            )
        )
    elif channel == "whatsapp":
        response = handle_whatsapp_message(
            WhatsAppWebhookPayload(
                **{
                    "from": phone,
                    "text": request.message.strip(),
                    "profile_name": user_id,
                    "message_id": new_id("portal_wa"),
                    "metadata": metadata,
                }
            )
        )
    else:
        raise HTTPException(status_code=400, detail="channel must be whatsapp or email")
    return {
        **response.model_dump(mode="json"),
        "contact_identifier": email if channel == "email" else phone,
        "graph": graph_status,
    }


def _web_chat_identity(user_id: str, user: dict) -> tuple[dict, str]:
    """Metadata that ties a web-chat message to the SAME customer as this user's
    other portal channels (see resolve_customer's portal/graph identifier priority
    in services/persistence_service/repository.py)."""
    email = str(user.get("email") or _portal_email(user_id)).strip().lower()
    metadata = {
        "portal_user_id": user_id,
        "portal_graph_customer_id": _resolve_graph_customer_id(user_id, email, _portal_phone(user_id)),
        "portal_contact_identifier": email,
        "linked_email": email,
        "source": "user_portal",
        "provider": "web_chat_portal",
    }
    return metadata, email


@router.get("/chat/messages")
def get_user_chat_messages(authorization: str | None = Header(default=None)) -> dict:
    user_id = _require_user(authorization)
    repo = get_repository()
    user = repo.get_customer_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user session")
    metadata, _ = _web_chat_identity(user_id, user)
    lookup_message = WebChatAdapter().normalize(
        WebChatWebhookPayload(session_id=user_id, text="", metadata=metadata)
    )
    customer = repo.resolve_customer(lookup_message)
    conversation = repo.get_or_create_conversation(customer["customer_id"])
    turns = repo.list_recent_turns(conversation["conversation_id"], limit=50, channel="web_chat")
    return {"conversation_id": conversation["conversation_id"], "turns": turns}


@router.post("/chat/messages")
def send_user_chat_message(
    request: UserChatMessageRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    user_id = _require_user(authorization)
    repo = get_repository()
    user = repo.get_customer_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user session")
    metadata, email = _web_chat_identity(user_id, user)
    graph_status = _upsert_customer_graph_user(user_id, email, "", "web_chat")
    payload = WebChatWebhookPayload(
        session_id=user_id,
        text=request.text.strip(),
        display_name=user_id,
        message_id=new_id("portal_webchat"),
        metadata=metadata,
    )
    response = get_router().handle(WebChatAdapter().normalize(payload))
    return {
        **response.model_dump(mode="json"),
        "contact_identifier": email,
        "graph": graph_status,
    }


def _ticket_summary(ticket: dict) -> dict:
    """One row per ticket for the customer portal — across all channels, open + closed.
    Channel is read from ticket metadata (the tickets table has no channel column)."""
    metadata = ticket.get("metadata") or {}
    return {
        "ticket_id": ticket.get("ticket_id"),
        "conversation_id": ticket.get("conversation_id"),
        "status": ticket.get("status") or "open",
        "channel": metadata.get("channel") or "-",
        "message": ticket.get("title") or (ticket.get("intent") or "").replace("_", " "),
        "created_at": ticket.get("created_at"),
        "updated_at": ticket.get("updated_at"),
    }


@router.get("/tickets")
def list_user_tickets(authorization: str | None = Header(default=None)) -> list[dict]:
    user_id = _require_user(authorization)
    repo = get_repository()
    tickets = repo.list_tickets()

    # Conversation ids this portal user owns (a turn tagged with their portal_user_id).
    owned_conversation_ids = set()
    for summary in repo.list_conversations():
        conversation = repo.get_conversation(summary["conversation_id"])
        if conversation and _owns_conversation(conversation, user_id):
            owned_conversation_ids.add(conversation["conversation_id"])

    # One row per ticket across ALL channels (open + closed): open group first, newest within.
    open_states = {"open", "in_progress"}
    owned_tickets = [t for t in tickets if t.get("conversation_id") in owned_conversation_ids]
    owned_tickets.sort(key=lambda t: t.get("created_at") or "", reverse=True)  # newest first
    owned_tickets.sort(key=lambda t: t.get("status") not in open_states)       # then open group first (stable)
    return [_ticket_summary(t) for t in owned_tickets]


@router.get("/tickets/{conversation_id}")
def get_user_ticket(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> dict:
    user_id = _require_user(authorization)
    repo = get_repository()
    conversation = repo.get_conversation(conversation_id)
    if not conversation or not _owns_conversation(conversation, user_id):
        raise HTTPException(status_code=404, detail="Ticket conversation not found")
    return _ticket_view(conversation, repo.list_tickets())


@router.get("/ticket-detail/{ticket_id}")
def get_user_ticket_detail(
    ticket_id: str,
    authorization: str | None = Header(default=None),
) -> dict:
    """Per-ticket detail (this ticket's own message + reply), not the conversation's latest.
    Multiple tickets share one conversation, so keying detail on ticket_id is required."""
    user_id = _require_user(authorization)
    repo = get_repository()
    ticket = repo.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    conversation = repo.get_conversation(ticket.get("conversation_id"))
    if not conversation or not _owns_conversation(conversation, user_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    # The ticket's own originating message is stored in its description/title.
    message = (ticket.get("description") or ticket.get("title") or "").replace(
        "Customer portal request\n\n", ""
    )
    # Full exchange history for this ticket (each customer message + its reply),
    # reconstructed from the conversation's chronological turns.
    turns = repo.list_conversation_turns(ticket.get("conversation_id"))
    exchanges = _build_ticket_exchanges(turns, ticket_id)
    return {
        "ticket_id": ticket_id,
        "status": ticket.get("status"),
        "channel": (ticket.get("metadata") or {}).get("channel"),
        # message / latest_response kept for backward compatibility.
        "message": message,
        "latest_response": repo.get_ticket_reply(ticket_id),
        "exchanges": exchanges,
        "created_at": ticket.get("created_at"),
    }
