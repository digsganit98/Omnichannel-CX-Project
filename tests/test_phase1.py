import hashlib
import hmac

import pytest
from fastapi import HTTPException

from apps.api.dependencies.security import (
    validate_email_secret,
    validate_local_whatsapp_test_signature,
    validate_whatsapp_signature,
)
from apps.api.routes import test_whatsapp
from services.agent_service.cx_agent import CXAgent
from services.channel_service.adapters.email_adapter import EmailAdapter
from services.channel_service.adapters.whatsapp_adapter import WhatsAppAdapter
from services.channel_service.delivery import OutboundDeliveryService
from services.intent_service.classifier import classify_intent
from services.orchestration_service.graph import OrchestrationGraph
from services.persistence_service.repository import SQLiteCXRepository
from shared.schemas.intents import Intent
from shared.schemas.messages import EmailWebhookPayload, WhatsAppWebhookPayload


class NoLLM:
    model = "test"

    def classify_message(self, message, context):
        return None


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


def graph(repository, whatsapp=None, email=None):
    return OrchestrationGraph(
        repository,
        agent=CXAgent(NoLLM()),
        rag=FakeRAG(),
        delivery=OutboundDeliveryService(whatsapp=whatsapp, email=email),
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
    assert response.outbound_status == "sent"
    assert sender.sent
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


def test_low_confidence_retrieval_creates_ticket():
    repo = SQLiteCXRepository(":memory:")
    response = graph(repo).run(whatsapp_message(text="unknown question"))
    assert response.ticket_id
    assert repo.get_ticket(response.ticket_id)


def test_email_authentication_failure(monkeypatch):
    monkeypatch.setenv("EMAIL_WEBHOOK_SECRET", "expected")
    with pytest.raises(HTTPException) as exc:
        validate_email_secret("wrong")
    assert exc.value.status_code == 401


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
