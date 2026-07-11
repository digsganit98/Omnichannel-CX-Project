from fastapi import HTTPException

from apps.api.routes import user_portal
from shared.schemas.responses import ChannelResponse


def _response(channel: str) -> ChannelResponse:
    return ChannelResponse(
        correlation_id="corr-1",
        conversation_id="conv-1",
        customer_id="cust-1",
        message=f"Reply via {channel}",
        resolved=False,
        intent="complaint",
        sentiment="negative",
        urgency="high",
        confidence=0.9,
        ticket_id="tkt-1",
        workflow_status="human_follow_up",
    )


def test_customer_signup_and_login_do_not_require_admin_key(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "user-portal-test-secret")
    monkeypatch.setenv("NEO4J_ENABLED", "false")
    from services.persistence_service.repository import SQLiteCXRepository

    repo = SQLiteCXRepository(":memory:")
    monkeypatch.setattr(user_portal, "get_repository", lambda: repo)
    signup = user_portal.user_signup(
        user_portal.UserSignupRequest(
            user_id="customer-1001",
            email="customer1001@example.com",
            password="portal-password",
        )
    )
    result = user_portal.user_login(
        user_portal.UserLoginRequest(user_id="customer-1001", password="portal-password")
    )

    assert signup["user"]["email"] == "customer1001@example.com"
    assert signup["graph"]["enabled"] is False
    assert result["user"]["user_id"] == "customer-1001"
    assert result["user"]["role"] == "customer"
    assert user_portal._require_user(f"Bearer {result['token']}") == "customer-1001"


def test_user_login_rejects_wrong_demo_password(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "user-portal-test-secret")
    monkeypatch.setenv("NEO4J_ENABLED", "false")
    from services.persistence_service.repository import SQLiteCXRepository

    repo = SQLiteCXRepository(":memory:")
    monkeypatch.setattr(user_portal, "get_repository", lambda: repo)
    user_portal.user_signup(
        user_portal.UserSignupRequest(
            user_id="customer-1001",
            email="customer1001@example.com",
            password="portal-password",
        )
    )

    try:
        user_portal.user_login(
            user_portal.UserLoginRequest(user_id="customer-1001", password="wrong")
        )
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected invalid demo password to be rejected")


def test_customer_signup_rejects_duplicate_user_id(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "user-portal-test-secret")
    monkeypatch.setenv("NEO4J_ENABLED", "false")
    from services.persistence_service.repository import SQLiteCXRepository

    repo = SQLiteCXRepository(":memory:")
    monkeypatch.setattr(user_portal, "get_repository", lambda: repo)
    request = user_portal.UserSignupRequest(
        user_id="customer-1001",
        email="customer1001@example.com",
        password="portal-password",
    )
    user_portal.user_signup(request)

    try:
        user_portal.user_signup(
            user_portal.UserSignupRequest(
                user_id="customer-1001",
                email="another@example.com",
                password="portal-password",
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("Expected duplicate user ID to be rejected")


def test_user_message_reuses_email_handler_and_tags_portal_user(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "user-portal-test-secret")
    monkeypatch.setenv("NEO4J_ENABLED", "false")
    from services.persistence_service.repository import SQLiteCXRepository

    repo = SQLiteCXRepository(":memory:")
    monkeypatch.setattr(user_portal, "get_repository", lambda: repo)
    user_portal.user_signup(
        user_portal.UserSignupRequest(
            user_id="customer-1001",
            email="customer1001@example.com",
            password="portal-password",
        )
    )
    captured = {}

    def fake_email_handler(payload):
        captured["payload"] = payload
        return _response("email")

    monkeypatch.setattr(user_portal, "handle_email_message", fake_email_handler)
    token = user_portal._make_token("customer-1001")

    result = user_portal.submit_user_message(
        user_portal.UserMessageRequest(
            channel="email",
            message="Please help with my loan.",
            contact_identifier="test.customer@example.com",
        ),
        authorization=f"Bearer {token}",
    )

    assert result["ticket_id"] == "tkt-1"
    assert result["contact_identifier"] == "test.customer@example.com"
    assert captured["payload"].from_email == "test.customer@example.com"
    assert captured["payload"].body == "Please help with my loan."
    assert captured["payload"].metadata["portal_user_id"] == "customer-1001"
    assert captured["payload"].metadata["linked_email"] == "test.customer@example.com"
    assert captured["payload"].metadata["source"] == "user_portal"
    assert result["graph"]["enabled"] is False


def test_user_message_uses_selected_whatsapp_number(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "user-portal-test-secret")
    monkeypatch.setenv("NEO4J_ENABLED", "false")
    from services.persistence_service.repository import SQLiteCXRepository

    repo = SQLiteCXRepository(":memory:")
    monkeypatch.setattr(user_portal, "get_repository", lambda: repo)
    user_portal.user_signup(
        user_portal.UserSignupRequest(
            user_id="customer-1001",
            email="customer1001@example.com",
            password="portal-password",
        )
    )
    captured = {}

    def fake_whatsapp_handler(payload):
        captured["payload"] = payload
        return _response("whatsapp")

    monkeypatch.setattr(user_portal, "handle_whatsapp_message", fake_whatsapp_handler)
    token = user_portal._make_token("customer-1001")

    result = user_portal.submit_user_message(
        user_portal.UserMessageRequest(
            channel="whatsapp",
            message="Please help with my card.",
            contact_identifier="+91 98765 43210",
        ),
        authorization=f"Bearer {token}",
    )

    assert captured["payload"].from_ == "919876543210"
    assert captured["payload"].metadata["provider"] == "whatsapp_cloud"
    assert captured["payload"].metadata["outbound_provider"] == "meta"
    assert captured["payload"].metadata["linked_email"] == "customer1001@example.com"
    assert captured["payload"].metadata["linked_phone"] == "919876543210"
    assert result["contact_identifier"] == "919876543210"
    assert result["graph"]["enabled"] is False


def test_portal_identity_prevents_shared_phone_from_reusing_previous_customer(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "user-portal-test-secret")
    monkeypatch.setenv("NEO4J_ENABLED", "false")
    from services.channel_service.adapters.whatsapp_adapter import WhatsAppAdapter
    from services.persistence_service.repository import SQLiteCXRepository
    from shared.schemas.messages import WhatsAppWebhookPayload

    repo = SQLiteCXRepository(":memory:")
    shared_phone = "917890864700"
    first = WhatsAppAdapter().normalize(
        WhatsAppWebhookPayload(
            **{
                "from": shared_phone,
                "text": "First user message",
                "profile_name": "Kishor",
                "metadata": {
                    "portal_user_id": "Kishor",
                    "portal_graph_customer_id": "CUST585097",
                    "linked_email": "kishor@gmail.com",
                    "linked_phone": shared_phone,
                },
            }
        )
    )
    second = WhatsAppAdapter().normalize(
        WhatsAppWebhookPayload(
            **{
                "from": shared_phone,
                "text": "Second user message",
                "profile_name": "Sayantini",
                "metadata": {
                    "portal_user_id": "Sayantini",
                    "portal_graph_customer_id": "CUST339640",
                    "linked_email": "sayantini.s.55@gmail.com",
                    "linked_phone": shared_phone,
                },
            }
        )
    )

    first_customer = repo.resolve_customer(first)
    second_customer = repo.resolve_customer(second)
    second_ids = repo.list_customer_identifiers(second_customer["customer_id"])

    assert first_customer["customer_id"] != second_customer["customer_id"]
    assert second_customer["display_name"] == "Sayantini"
    assert {"channel": "portal", "identifier": "Sayantini"} in second_ids
    assert {"channel": "graph", "identifier": "CUST339640"} in second_ids
    assert {"channel": "email", "identifier": "sayantini.s.55@gmail.com"} in second_ids


def test_customer_signup_and_contact_updates_are_written_to_neo4j(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "user-portal-test-secret")
    monkeypatch.setenv("NEO4J_ENABLED", "true")
    from services.neo4j_service import client as client_module
    from services.neo4j_service import writer as writer_module
    from services.persistence_service.repository import SQLiteCXRepository

    repo = SQLiteCXRepository(":memory:")
    monkeypatch.setattr(user_portal, "get_repository", lambda: repo)
    customer_calls = []
    seed_calls = []

    class FakeNeo4jClient:
        def close(self):
            pass

    def fake_upsert(client, **kwargs):
        customer_calls.append(kwargs)

    def fake_seed(client, **kwargs):
        seed_calls.append(kwargs)
        return {"loans": 2, "claims": 2, "policies": 2, "kyc": 1, "product_links": 2}

    monkeypatch.setattr(client_module, "Neo4jClient", FakeNeo4jClient)
    monkeypatch.setattr(writer_module, "upsert_customer", fake_upsert)
    monkeypatch.setattr(writer_module, "seed_synthetic_bfsi_records", fake_seed)
    monkeypatch.setattr(user_portal, "handle_whatsapp_message", lambda payload: _response("whatsapp"))

    signup = user_portal.user_signup(
        user_portal.UserSignupRequest(
            user_id="customer-graph-1",
            email="graph.customer@example.com",
            password="portal-password",
        )
    )
    result = user_portal.submit_user_message(
        user_portal.UserMessageRequest(
            channel="whatsapp",
            message="Please help with my claim.",
            contact_identifier="+91 77009 20746",
        ),
        authorization=f"Bearer {signup['token']}",
    )

    assert signup["graph"]["status"] == "upserted"
    assert result["graph"]["status"] == "upserted"
    assert signup["graph"]["synthetic_records"] == {
        "loans": 2,
        "claims": 2,
        "policies": 2,
        "kyc": 1,
        "product_links": 2,
    }
    assert customer_calls[0]["customer_id"].startswith("CUST")
    assert customer_calls[0]["customer_id"][4:].isdigit()
    assert customer_calls[0] == {
        "customer_id": customer_calls[0]["customer_id"],
        "phone": "",
        "email": "graph.customer@example.com",
        "secondary_email": "",
        "city": "",
        "country": "India",
        "registration_date": customer_calls[0]["registration_date"],
        "last_activity_date": customer_calls[0]["last_activity_date"],
        "name": "customer-graph-1",
        "channel": "portal",
    }
    assert seed_calls[0] == {
        "customer_id": customer_calls[0]["customer_id"],
        "registration_date": customer_calls[0]["registration_date"],
        "email": "graph.customer@example.com",
        "phone": "",
    }
    assert customer_calls[0]["registration_date"].count("/") == 2
    assert customer_calls[0]["last_activity_date"].count("/") == 2
    assert customer_calls[1] == {
        "customer_id": customer_calls[0]["customer_id"],
        "phone": "917700920746",
        "email": "graph.customer@example.com",
        "secondary_email": "",
        "city": "",
        "country": "India",
        "registration_date": customer_calls[1]["registration_date"],
        "last_activity_date": customer_calls[1]["last_activity_date"],
        "name": "customer-graph-1",
        "channel": "whatsapp",
    }
    assert seed_calls[1] == {
        "customer_id": customer_calls[0]["customer_id"],
        "registration_date": customer_calls[1]["registration_date"],
        "email": "graph.customer@example.com",
        "phone": "917700920746",
    }


def test_web_chat_message_tags_portal_identity(monkeypatch):
    """POST /user/chat/messages must route through the SAME identity mechanism as the
    existing whatsapp/email portal messages (portal_user_id/portal_graph_customer_id in
    metadata), not an anonymous session — this is what ties web chat to the real customer."""
    monkeypatch.setenv("JWT_SECRET", "user-portal-test-secret")
    monkeypatch.setenv("NEO4J_ENABLED", "false")
    from services.persistence_service.repository import SQLiteCXRepository

    repo = SQLiteCXRepository(":memory:")
    monkeypatch.setattr(user_portal, "get_repository", lambda: repo)
    user_portal.user_signup(
        user_portal.UserSignupRequest(
            user_id="customer-3001",
            email="customer3001@example.com",
            password="portal-password",
        )
    )
    token = user_portal._make_token("customer-3001")
    captured = {}

    class CapturingRouter:
        def handle(self, message):
            captured["message"] = message
            return _response("web_chat")

    monkeypatch.setattr(user_portal, "get_router", lambda: CapturingRouter())

    result = user_portal.send_user_chat_message(
        user_portal.UserChatMessageRequest(text="Hello there"),
        authorization=f"Bearer {token}",
    )

    message = captured["message"]
    assert message.channel.value == "web_chat"
    assert message.text == "Hello there"
    assert message.metadata["portal_user_id"] == "customer-3001"
    assert message.metadata["source"] == "user_portal"
    assert message.metadata["provider"] == "web_chat_portal"
    assert result["contact_identifier"] == "customer3001@example.com"


def test_web_chat_message_and_history_round_trip(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "user-portal-test-secret")
    monkeypatch.setenv("NEO4J_ENABLED", "false")
    from services.persistence_service.repository import SQLiteCXRepository

    repo = SQLiteCXRepository(":memory:")
    monkeypatch.setattr(user_portal, "get_repository", lambda: repo)
    user_portal.user_signup(
        user_portal.UserSignupRequest(
            user_id="customer-2001",
            email="customer2001@example.com",
            password="portal-password",
        )
    )
    token = user_portal._make_token("customer-2001")

    class FakeRouter:
        """Minimal stand-in for OmnichannelRouter that persists turns like the real
        orchestration graph does, so the history endpoint has something to read back."""

        def handle(self, message):
            customer = repo.resolve_customer(message)
            conversation = repo.get_or_create_conversation(customer["customer_id"])
            repo.append_turn(
                conversation_id=conversation["conversation_id"], customer_id=customer["customer_id"],
                channel=message.channel.value, direction="inbound", text=message.text,
                metadata=message.metadata,
            )
            repo.append_turn(
                conversation_id=conversation["conversation_id"], customer_id=customer["customer_id"],
                channel=message.channel.value, direction="outbound", text="Thanks, we'll help with that.",
                metadata={},
            )
            return _response("web_chat").model_copy(update={
                "conversation_id": conversation["conversation_id"],
                "customer_id": customer["customer_id"],
                "message": "Thanks, we'll help with that.",
            })

    monkeypatch.setattr(user_portal, "get_router", lambda: FakeRouter())

    sent = user_portal.send_user_chat_message(
        user_portal.UserChatMessageRequest(text="Hi, I need help with my loan."),
        authorization=f"Bearer {token}",
    )
    assert sent["message"] == "Thanks, we'll help with that."

    history = user_portal.get_user_chat_messages(authorization=f"Bearer {token}")
    texts = [turn["text"] for turn in history["turns"]]
    assert "Hi, I need help with my loan." in texts
    assert "Thanks, we'll help with that." in texts
    assert history["conversation_id"] == sent["conversation_id"]


def test_chat_endpoints_require_login():
    try:
        user_portal.get_user_chat_messages(authorization=None)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected missing auth to be rejected")


def test_user_ticket_list_is_scoped_to_portal_user(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "user-portal-test-secret")

    class FakeRepository:
        def list_tickets(self):
            return [
                {
                    "ticket_id": "tkt-mine",
                    "conversation_id": "conv-mine",
                    "status": "open",
                },
                {
                    "ticket_id": "tkt-other",
                    "conversation_id": "conv-other",
                    "status": "open",
                },
            ]

        def list_conversations(self):
            return [{"conversation_id": "conv-mine"}, {"conversation_id": "conv-other"}]

        def get_conversation(self, conversation_id):
            owner = "customer-1001" if conversation_id == "conv-mine" else "someone-else"
            return {
                "conversation_id": conversation_id,
                "status": "active",
                "created_at": "2026-06-07T10:00:00Z",
                "updated_at": "2026-06-07T10:01:00Z",
                "turns": [
                    {
                        "direction": "inbound",
                        "channel": "whatsapp",
                        "text": "Need help",
                        "metadata": {"portal_user_id": owner},
                    },
                    {
                        "direction": "outbound",
                        "channel": "whatsapp",
                        "text": "We are reviewing this.",
                        "metadata": {},
                    },
                ],
            }

    monkeypatch.setattr(user_portal, "get_repository", lambda: FakeRepository())
    token = user_portal._make_token("customer-1001")

    tickets = user_portal.list_user_tickets(authorization=f"Bearer {token}")

    assert [ticket["ticket_id"] for ticket in tickets] == ["tkt-mine"]
    assert tickets[0]["latest_response"] == "We are reviewing this."
