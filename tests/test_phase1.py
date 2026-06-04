import hashlib
import hmac
import json

import pytest
from fastapi import HTTPException

from apps.api.dependencies.security import (
    validate_email_secret,
    validate_local_whatsapp_test_signature,
    validate_whatsapp_signature,
)
from apps.api.routes import integrations, test_whatsapp, whatsapp as whatsapp_admin
from services.agent_service.cx_agent import CXAgent
from services.channel_service.adapters.email_adapter import EmailAdapter
from services.channel_service.adapters.whatsapp_adapter import WhatsAppAdapter
from services.channel_service.connectors.email_sender import SMTPEmailConnector
from services.channel_service.delivery import OutboundDeliveryService
from services.crm_service.client import CRMResult
from services.intent_service.classifier import classify_intent
from services.orchestration_service.graph import OrchestrationGraph
from services.persistence_service.repository import SQLiteCXRepository
from services.rag_service.embeddings import SemanticEmbeddings
from services.rag_service.documents import load_knowledge_documents
from services.rag_service.generator import OllamaGenerator
from services.rag_service.rag_pipeline import RAGPipeline
from shared.schemas.intents import Intent
from shared.schemas.messages import EmailWebhookPayload, WhatsAppWebhookPayload
from shared.schemas.tickets import TicketStatus


class NoLLM:
    model = "test"

    def classify_message(self, message, context):
        return None


class ValidLLM:
    def classify_message(self, message, context):
        return {
            "intent": "order_tracking",
            "confidence": 0.9,
            "urgency": "low",
            "sentiment": "neutral",
            "reason": "Customer asked for shipment tracking.",
        }


class UnderstatedLLM:
    def classify_message(self, message, context):
        return {
            "intent": "refund_request",
            "confidence": 1.0,
            "urgency": "low",
            "sentiment": "positive",
            "reason": "Customer requested a refund.",
        }


class FakeRAG:
    def answer(self, query, context):
        if "unknown" in query.lower():
            return {"answer": "manual review", "confidence": 0.0, "contexts": [], "citations": [], "llm": {}}
        context_item = {
            "text": "Customers can track orders after dispatch.",
            "score": 0.91,
            "metadata": {"source": "orders.md", "document_version": "test-v1"},
        }
        return {
            "answer": "Customers can track orders after dispatch. Source: [1] orders.md",
            "confidence": 0.91,
            "contexts": [context_item],
            "citations": [{"index": 1, "source": "orders.md", "score": 0.91}],
            "llm": {"llm_used": False},
        }


class Recorder:
    def __init__(self):
        self.sent = []

    def send_text(self, *args):
        self.sent.append(args)
        return {"id": "provider-message-id"}


def graph(repository, whatsapp=None, email=None, crm=None):
    return OrchestrationGraph(
        repository,
        agent=CXAgent(NoLLM()),
        rag=FakeRAG(),
        delivery=OutboundDeliveryService(whatsapp=whatsapp, email=email),
        crm=crm,
    )


def whatsapp_message(message_id="wamid-1", text="Where is my order?", metadata=None):
    return WhatsAppAdapter().normalize(
        WhatsAppWebhookPayload(
            from_="+919999999999",
            text=text,
            message_id=message_id,
            metadata={"provider": "whatsapp_cloud", **(metadata or {})},
        )
    )


def email_message(message_id="email-1", body="Where is my order?", metadata=None):
    return EmailAdapter().normalize(
        EmailWebhookPayload(
            from_email="customer@example.com",
            subject="Customer request",
            body=body,
            message_id=message_id,
            metadata={"provider": "email_webhook", **(metadata or {})},
        )
    )


def test_whatsapp_order_query_resolves_with_citation_and_sends_reply():
    repo = SQLiteCXRepository(":memory:")
    sender = Recorder()
    response = graph(repo, whatsapp=sender).run(whatsapp_message())
    assert response.resolved is True
    assert response.intent == "order_tracking"
    assert response.citations[0]["source"] == "orders.md"
    assert response.retrieval_backend == "unknown"
    assert response.outbound_status == "sent"
    assert sender.sent
    ticket_step = next(entry for entry in response.workflow_trace if entry["step"] == "create_or_update_ticket")
    assert ticket_step["details"]["skipped"] is True
    evidence = repo.list_retrieval_evidence()
    assert evidence[0]["source"] == "orders.md"


def test_email_complaint_escalates_and_sends_reply():
    repo = SQLiteCXRepository(":memory:")
    sender = Recorder()
    response = graph(repo, email=sender).run(email_message(body="This is an unacceptable complaint. I need a human."))
    assert response.resolved is False
    assert response.intent in {"complaint", "human_escalation"}
    assert response.ticket_id
    assert response.outbound_status == "sent"
    assert sender.sent
    ticket_step = next(entry for entry in response.workflow_trace if entry["step"] == "create_or_update_ticket")
    assert "skipped" not in ticket_step["details"]


def test_outbound_failure_error_is_returned_in_channel_response():
    class FailingSender:
        def send_text(self, *args):
            raise RuntimeError("provider rejected recipient")

    repo = SQLiteCXRepository(":memory:")
    response = graph(repo, whatsapp=FailingSender()).run(whatsapp_message())

    assert response.outbound_status == "failed"
    assert response.outbound_error == "provider rejected recipient"


def test_duplicate_message_returns_original_response_without_second_send():
    repo = SQLiteCXRepository(":memory:")
    sender = Recorder()
    workflow = graph(repo, whatsapp=sender)
    first = workflow.run(whatsapp_message())
    second = workflow.run(whatsapp_message())
    assert second.duplicate is True
    assert first.conversation_id == second.conversation_id
    assert len(sender.sent) == 1


def test_customer_identity_resolution_links_email_and_whatsapp():
    repo = SQLiteCXRepository(":memory:")
    workflow = graph(repo)
    first = workflow.run(whatsapp_message(metadata={"linked_email": "customer@example.com"}))
    second = workflow.run(email_message())
    assert first.customer_id == second.customer_id
    assert first.conversation_id == second.conversation_id


def test_multi_turn_context_is_persisted():
    repo = SQLiteCXRepository(":memory:")
    workflow = graph(repo)
    response = workflow.run(whatsapp_message())
    workflow.run(whatsapp_message(message_id="wamid-2", text="Can you check that order again?"))
    conversation = repo.get_conversation(response.conversation_id)
    assert len(conversation["turns"]) == 4
    assert "check that order again" in conversation["summary"]


def test_customer_message_can_resolve_active_ticket_without_rag():
    repo = SQLiteCXRepository(":memory:")
    sender = Recorder()
    workflow = graph(repo, whatsapp=sender)
    opened = workflow.run(
        whatsapp_message(message_id="wamid-open", text="This is a complaint. Please connect me to a human.")
    )
    closed = workflow.run(
        whatsapp_message(message_id="wamid-close", text="close the ticket as query is resolved, thanks")
    )

    assert opened.ticket_id
    assert closed.ticket_id == opened.ticket_id
    assert closed.intent == "ticket_resolution"
    assert closed.resolved is True
    assert closed.next_best_action == "ticket_closed"
    assert closed.retrieval_backend == "not_required"
    assert closed.rag_contexts == []
    assert repo.get_ticket(opened.ticket_id)["status"] == TicketStatus.RESOLVED.value
    assert "marked as resolved" in closed.message
    assert [entry["step"] for entry in closed.workflow_trace] == [
        "receive_message",
        "resolve_identity",
        "load_conversation_context",
        "detect_ticket_action",
        "resolve_ticket",
        "send_outbound_reply",
        "persist_audit_events",
    ]


def test_restart_persistence(tmp_path):
    database = str(tmp_path / "phase1.db")
    first_repo = SQLiteCXRepository(database)
    response = graph(first_repo).run(whatsapp_message())
    second_repo = SQLiteCXRepository(database)
    conversation = second_repo.get_conversation(response.conversation_id)
    assert conversation
    assert len(conversation["turns"]) == 2
    assert second_repo.list_audit_events(response.correlation_id)


def test_intent_classifier_supports_phase1_intents():
    assert classify_intent("Please refund my payment").intent == Intent.REFUND_REQUEST
    assert classify_intent("Is this product available in blue?").intent == Intent.PRODUCT_INFORMATION
    assert classify_intent("I want a human representative").intent == Intent.HUMAN_ESCALATION


def test_llm_intent_result_accepts_model_reason():
    result = CXAgent(ValidLLM()).analyze("Where is my shipment?")
    assert result.intent == Intent.ORDER_TRACKING
    assert result.reason == "Customer asked for shipment tracking."
    assert result.analysis_source == "ollama_llm"


def test_llm_intent_guardrails_raise_understated_sentiment_and_urgency():
    result = CXAgent(UnderstatedLLM()).analyze(
        "I want refund, and cancel my order. Connect me to an human agent immediately."
    )
    assert result.intent == Intent.REFUND_REQUEST
    assert result.sentiment == "negative"
    assert result.urgency.value == "high"
    assert "Deterministic guardrails raised: sentiment, urgency." in result.reason


def test_low_confidence_retrieval_creates_ticket():
    repo = SQLiteCXRepository(":memory:")
    response = graph(repo).run(whatsapp_message(text="unknown question"))
    assert response.ticket_id
    assert repo.get_ticket(response.ticket_id)


def test_customer_answer_kb_excludes_uploaded_ticket_history():
    documents = load_knowledge_documents()
    assert documents
    assert {document.metadata["doc_type"] for document in documents} == {"knowledge_base"}
    assert all(document.metadata["source"].endswith(".pdf") for document in documents)


def test_rag_discards_non_kb_contexts_before_generation():
    class UnsafeStore:
        def similarity_search(self, query, k):
            return [
                {
                    "text": "Customer: Example Name | Order ID: O123",
                    "score": 0.99,
                    "metadata": {"source": "ticket-export.json", "doc_type": "ticket_history"},
                },
                {
                    "text": "Approved refund policy.",
                    "score": 0.8,
                    "metadata": {"source": "refunds.md", "doc_type": "knowledge_base"},
                },
            ]

    class ContextRecorder:
        def generate_answer(self, query, contexts, conversation_context):
            assert [context["metadata"]["source"] for context in contexts] == ["refunds.md"]
            return {"text": "Approved answer.", "llm_used": True}

    answer = RAGPipeline(store=UnsafeStore(), generator=ContextRecorder()).answer("refund policy")
    assert [context["metadata"]["source"] for context in answer["contexts"]] == ["refunds.md"]


def test_email_authentication_failure(monkeypatch):
    monkeypatch.setenv("EMAIL_WEBHOOK_SECRET", "expected")
    with pytest.raises(HTTPException) as exc:
        validate_email_secret("wrong")
    assert exc.value.status_code == 401


def test_gmail_smtp_status_and_send(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["host"] = host
            sent["port"] = port
            sent["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def ehlo(self):
            sent["ehlo"] = sent.get("ehlo", 0) + 1

        def starttls(self):
            sent["starttls"] = True

        def login(self, username, password):
            sent["username"] = username
            sent["password"] = password

        def send_message(self, message):
            sent["to"] = message["To"]
            sent["subject"] = message["Subject"]
            return {}

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "support@example.com")
    monkeypatch.setenv("SMTP_USERNAME", "support@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_USE_TLS", "true")
    monkeypatch.setenv("SMTP_USE_SSL", "false")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    connector = SMTPEmailConnector()
    assert connector.status()["gmail_ready"] is True
    result = connector.send_text("customer@example.com", "Test", "Hello")

    assert result["status"] == "sent"
    assert sent["host"] == "smtp.gmail.com"
    assert sent["port"] == 587
    assert sent["starttls"] is True
    assert sent["username"] == "support@example.com"
    assert sent["to"] == "customer@example.com"


def test_whatsapp_signature_validation(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    body = b'{"entry":[]}'
    signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    validate_whatsapp_signature(body, signature)
    with pytest.raises(HTTPException):
        validate_whatsapp_signature(body, "sha256=wrong")


def test_local_whatsapp_test_signature_is_gated(monkeypatch):
    monkeypatch.setenv("WHATSAPP_LOCAL_TEST_MODE", "false")
    monkeypatch.setenv("WHATSAPP_TEST_SIGNATURE", "local-secret")
    with pytest.raises(HTTPException) as exc:
        validate_local_whatsapp_test_signature("local-secret")
    assert exc.value.status_code == 404

    monkeypatch.setenv("WHATSAPP_LOCAL_TEST_MODE", "true")
    validate_local_whatsapp_test_signature("local-secret")
    with pytest.raises(HTTPException) as exc:
        validate_local_whatsapp_test_signature("wrong")
    assert exc.value.status_code == 401


def test_local_whatsapp_inbound_uses_mock_outbound_provider(monkeypatch):
    monkeypatch.setenv("WHATSAPP_LOCAL_TEST_MODE", "true")
    repo = SQLiteCXRepository(":memory:")
    workflow = graph(repo)
    message = whatsapp_message(metadata={"provider": "whatsapp_local_test"})
    response = workflow.run(message)
    events = repo.list_audit_events(response.correlation_id)
    outbound = next(event for event in events if event["event_type"] == "outbound_sent")
    assert outbound["details"]["provider_response"]["provider"] == "whatsapp_local_test"


def test_local_whatsapp_inbound_can_request_meta_outbound_provider(monkeypatch):
    captured = {}

    def fake_handle_whatsapp_message(payload):
        captured["provider"] = payload.metadata["provider"]
        captured["outbound_provider"] = payload.metadata["outbound_provider"]

        class FakeResponse:
            def model_dump(self, mode=None):
                return {"ok": True}

        return FakeResponse()

    monkeypatch.setenv("WHATSAPP_LOCAL_TEST_MODE", "true")
    monkeypatch.setenv("WHATSAPP_TEST_SIGNATURE", "local-secret")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "meta-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setattr(test_whatsapp, "handle_whatsapp_message", fake_handle_whatsapp_message)

    result = test_whatsapp.simulate_whatsapp_inbound(
        test_whatsapp.LocalWhatsAppInbound(
            from_="919999999999",
            text="Where is my order?",
            outbound_provider="meta",
        ),
        x_test_whatsapp_signature="local-secret",
    )

    assert result == {"ok": True}
    assert captured == {"provider": "whatsapp_cloud", "outbound_provider": "meta"}


def test_local_whatsapp_manual_send_writes_audit_event(monkeypatch):
    monkeypatch.setenv("WHATSAPP_LOCAL_TEST_MODE", "true")
    monkeypatch.setenv("WHATSAPP_TEST_SIGNATURE", "local-secret")
    repo = SQLiteCXRepository(":memory:")
    monkeypatch.setattr(test_whatsapp, "get_repository", lambda: repo)
    result = test_whatsapp.simulate_whatsapp_send(
        test_whatsapp.LocalWhatsAppSend(to="919999999999", text="test reply"),
        x_test_whatsapp_signature="local-secret",
    )
    assert result["provider"] == "local_mock"
    assert result["status"] == "sent"
    assert repo.list_audit_events(result["correlation_id"])[0]["event_type"] == "local_whatsapp_test_sent"


def test_local_whatsapp_manual_meta_send_uses_cloud_connector(monkeypatch):
    monkeypatch.setenv("WHATSAPP_LOCAL_TEST_MODE", "true")
    monkeypatch.setenv("WHATSAPP_TEST_SIGNATURE", "local-secret")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "meta-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "phone-id")
    repo = SQLiteCXRepository(":memory:")
    monkeypatch.setattr(test_whatsapp, "get_repository", lambda: repo)

    class FakeMetaConnector:
        def __init__(self, access_token, phone_number_id):
            assert access_token == "meta-token"
            assert phone_number_id == "phone-id"

        def send_text(self, to, text):
            return {"messages": [{"id": "wamid-meta-test"}], "to": to, "text": text}

    monkeypatch.setattr(test_whatsapp, "WhatsAppCloudConnector", FakeMetaConnector)
    result = test_whatsapp.simulate_whatsapp_send(
        test_whatsapp.LocalWhatsAppSend(to="919999999999", text="real Meta test", provider="meta"),
        x_test_whatsapp_signature="local-secret",
    )
    assert result["provider"] == "meta"
    assert result["provider_response"]["messages"][0]["id"] == "wamid-meta-test"


def test_whatsapp_status_webhook_updates_outbound_turn_and_admin_lookup(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import app

    repo = SQLiteCXRepository(":memory:")

    class MetaSender:
        def send_text(self, to, text):
            return {"messages": [{"id": "wamid-meta-reply"}], "contacts": [{"wa_id": to}]}

    response = graph(repo, whatsapp=MetaSender()).run(whatsapp_message(metadata={"provider": "whatsapp_cloud"}))
    assert response.outbound_status == "sent"

    monkeypatch.setenv("WHATSAPP_APP_SECRET", "status-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "status-admin-key")
    monkeypatch.setattr(integrations, "get_repository", lambda: repo)
    monkeypatch.setattr(whatsapp_admin, "get_repository", lambda: repo)

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {
                                    "id": "wamid-meta-reply",
                                    "status": "delivered",
                                    "timestamp": "1710000000",
                                    "recipient_id": "918555870077",
                                    "conversation": {"id": "conv-meta"},
                                    "pricing": {"category": "service"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(b"status-secret", body, hashlib.sha256).hexdigest()

    client = TestClient(app)
    webhook = client.post(
        "/integrations/whatsapp/webhook",
        content=body,
        headers={"x-hub-signature-256": signature, "content-type": "application/json"},
    )

    assert webhook.status_code == 200
    assert webhook.json()["statuses_received"] == 1
    assert webhook.json()["statuses"][0]["status"] == "delivered"

    admin = client.get(
        "/admin/whatsapp/delivery-statuses",
        params={"provider_message_id": "wamid-meta-reply"},
        headers={"x-admin-key": "status-admin-key"},
    )

    assert admin.status_code == 200
    assert admin.json()[0]["status"] == "delivered"

    outbound_turn = next(
        turn
        for turn in repo.get_conversation(response.conversation_id)["turns"]
        if turn["direction"] == "outbound"
    )
    assert outbound_turn["delivery_status"] == "delivered"
    assert outbound_turn["metadata"]["provider_message_id"] == "wamid-meta-reply"


class FakeCRM:
    def lookup_customer(self, channel, identifier):
        return CRMResult("synced", {"customer_id": "crm-customer-001", "segment": "premium"})

    def create_ticket(self, ticket, customer=None):
        return CRMResult(
            "synced",
            {
                "external_ticket_id": "CRM-101",
                "external_ticket_url": "https://crm.example.test/tickets/CRM-101",
            },
        )

    def add_comment(self, external_ticket_id, comment):
        assert external_ticket_id == "CRM-101"
        return CRMResult("synced", {"comment_id": "comment-1"})

    def update_ticket_status(self, external_ticket_id, status):
        assert external_ticket_id == "CRM-101"
        return CRMResult("synced", {"status": status})


def test_ticket_crm_sync_profile_enrichment_and_lifecycle():
    repo = SQLiteCXRepository(":memory:")
    workflow = graph(repo, crm=FakeCRM())
    response = workflow.run(email_message(body="This is an unacceptable complaint. I need a human."))
    ticket = repo.get_ticket(response.ticket_id)
    assert ticket["external_ticket_id"] == "CRM-101"
    assert ticket["crm_sync_status"] == "synced"
    assert ticket["sla_due_at"]
    assert ticket["escalation_reason"].startswith("manual_review_required")

    manager = workflow.tickets
    comment = manager.add_comment(response.ticket_id, "Investigating with fulfillment.")
    assert comment["details"]["crm_sync_status"] == "synced"
    updated = manager.update_status(response.ticket_id, TicketStatus.IN_PROGRESS)
    assert updated["status"] == "in_progress"
    assert [event["event_type"] for event in repo.list_ticket_events(response.ticket_id)] == [
        "ticket_created",
        "crm_sync_synced",
        "comment_added",
        "status_updated",
    ]


def test_admin_ui_is_served():
    from fastapi.testclient import TestClient

    from apps.api.main import app

    response = TestClient(app).get("/admin-ui")
    assert response.status_code == 200
    assert "Ticket Operations" in response.text
    assert "email-simulate-form" in response.text


def test_email_admin_routes_are_protected(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import app

    monkeypatch.setenv("ADMIN_API_KEY", "email-admin-key")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "support@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_USE_TLS", "true")
    client = TestClient(app)

    assert client.get("/admin/email/status").status_code == 401
    response = client.get("/admin/email/status", headers={"x-admin-key": "email-admin-key"})

    assert response.status_code == 200
    assert response.json()["gmail_ready"] is True


def test_whatsapp_admin_status_reports_meta_readiness(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import app

    monkeypatch.setenv("ADMIN_API_KEY", "whatsapp-admin-key")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "meta-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "waba-id")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify-token")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    client = TestClient(app)

    assert client.get("/admin/whatsapp/status").status_code == 401
    response = client.get("/admin/whatsapp/status", headers={"x-admin-key": "whatsapp-admin-key"})

    assert response.status_code == 200
    assert response.json()["meta_outbound_ready"] is True
    assert response.json()["meta_webhook_ready"] is True
    assert response.json()["business_account_id_configured"] is True


def test_orchestration_trace_records_explicit_agent_workflow():
    repo = SQLiteCXRepository(":memory:")
    response = graph(repo).run(whatsapp_message())
    steps = [entry["step"] for entry in response.workflow_trace]
    assert steps == [
        "receive_message",
        "resolve_identity",
        "load_conversation_context",
        "detect_ticket_action",
        "classify_intent",
        "retrieve_knowledge",
        "decide_resolution",
        "create_or_update_ticket",
        "send_outbound_reply",
        "persist_audit_events",
    ]
    events = repo.list_audit_events(response.correlation_id)
    agent_actions = [event for event in events if event["event_type"] == "workflow_step_completed"]
    assert len(agent_actions) == len(steps)
    assert events[-1]["event_type"] == "workflow_completed"


def test_orchestration_workflow_definition_is_admin_protected(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import app

    monkeypatch.setenv("ADMIN_API_KEY", "workflow-test-admin-key")
    client = TestClient(app)
    assert client.get("/admin/orchestration/workflow").status_code == 401
    response = client.get(
        "/admin/orchestration/workflow",
        headers={"x-admin-key": "workflow-test-admin-key"},
    )
    assert response.status_code == 200
    assert response.json()["engine"] == "langgraph_state_graph"
    assert response.json()["framework"] == "LangGraph"
    assert len(response.json()["agents"]) == 4
    assert len(response.json()["edges"]) == 13
    assert response.json()["agents"][0]["execution"] == "ollama_llm_with_validated_rule_fallback"


def test_hashing_embeddings_are_an_explicit_fallback(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "hashing")
    embeddings = SemanticEmbeddings()
    assert embeddings.status()["active_backend"] == "hashing_fallback"
    assert len(embeddings.embed_query("Track my order")) == 384


def test_ollama_can_be_explicitly_disabled(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "false")
    result = OllamaGenerator().generate_answer("question", [])
    assert result["llm_used"] is False
    assert result["error"] == "OLLAMA_ENABLED=false"
