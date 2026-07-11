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


def _xlsx_date_today() -> str:
    today = datetime.now()
    return f"{today.month}/{today.day}/{str(today.year)[-2:]}"


def _upsert_customer_graph_user(user_id: str, email: str, phone: str = "", channel: str = "portal") -> dict:
    if os.getenv("NEO4J_ENABLED", "true").lower() != "true":
        return {"enabled": False, "customer_id": _graph_customer_id(user_id)}
    client = None
    try:
        from services.neo4j_service.client import Neo4jClient
        from services.neo4j_service.writer import seed_synthetic_bfsi_records, upsert_customer

        client = Neo4jClient()
        graph_customer_id = _graph_customer_id(user_id)
        today = _xlsx_date_today()
        upsert_customer(
            client,
            customer_id=graph_customer_id,
            phone=phone,
            email=email,
            secondary_email="",
            city="",
            country="India",
            registration_date=today,
            last_activity_date=today,
            name=user_id,
            channel=channel,
        )
        synthetic = seed_synthetic_bfsi_records(
            client,
            customer_id=graph_customer_id,
            registration_date=today,
            email=email,
            phone=phone,
        )
        return {
            "enabled": True,
            "status": "upserted",
            "customer_id": graph_customer_id,
            "synthetic_records": synthetic,
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
        "portal_graph_customer_id": _graph_customer_id(user_id),
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
        "portal_graph_customer_id": _graph_customer_id(user_id),
        "portal_contact_identifier": email,
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
    turns = repo.list_recent_turns(conversation["conversation_id"], limit=50)
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


@router.get("/tickets")
def list_user_tickets(authorization: str | None = Header(default=None)) -> list[dict]:
    user_id = _require_user(authorization)
    repo = get_repository()
    tickets = repo.list_tickets()
    results = []
    for summary in repo.list_conversations():
        conversation = repo.get_conversation(summary["conversation_id"])
        if conversation and _owns_conversation(conversation, user_id):
            results.append(_ticket_view(conversation, tickets))
    return results


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
