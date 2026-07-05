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
from services.orchestration_service.router import OmnichannelRouter
from services.persistence_service.repository import SQLiteCXRepository
from services.rag_service.embeddings import SemanticEmbeddings
from services.rag_service.documents import load_knowledge_documents
from services.rag_service.rag_pipeline import RAGPipeline
from shared.schemas.intents import Intent
from shared.schemas.messages import EmailWebhookPayload, WhatsAppWebhookPayload
from shared.schemas.tickets import TicketStatus


# ── Mock LLM generators ───────────────────────────────────────────────────────

class NoLLM:
    model = "test"

    def classify_message(self, message, context):
        return None


class ValidLLM:
    """Returns a valid BFSI intent with high confidence."""
    def classify_message(self, message, context):
        return {
            "intent": "loan_status",
            "confidence": 0.9,
            "urgency": "low",
            "sentiment": "neutral",
            "reason": "Customer asked about their loan repayment status.",
        }


class UnderstatedLLM:
    """Returns an understated urgency/sentiment for a fraud message."""
    def classify_message(self, message, context):
        return {
            "intent": "fraud_report",
            "confidence": 1.0,
            "urgency": "low",
            "sentiment": "positive",
            "reason": "Customer reported fraud.",
        }


class FakeRAG:
    def answer(self, query, context):
        if "unknown" in query.lower():
            return {"answer": "manual review", "confidence": 0.0, "contexts": [], "citations": [], "llm": {}}
        context_item = {
            "text": "For loan EMI queries, customers can check their repayment schedule in the app.",
            "score": 0.91,
            "metadata": {"source": "InboxIQ_BFSI_KB.pdf:p3", "document_version": "test-v1"},
        }
        return {
            "answer": "You can check your loan repayment schedule in the app. Source: [1] InboxIQ_BFSI_KB.pdf:p3",
            "confidence": 0.91,
            "contexts": [context_item],
            "citations": [{"index": 1, "source": "InboxIQ_BFSI_KB.pdf:p3", "score": 0.91}],
            "llm": {"llm_used": False},
        }


class FakeNeo4j:
    """Stub Neo4j client that returns canned BFSI graph data."""

    def query(self, cypher, params=None):
        if "customer_id" in cypher and "$cid" in cypher and "Loan" in cypher:
            return [{"loan_id": "L001", "loan_type": "Personal Loan", "status": "Active",
                     "amount_inr": 500000, "interest_rate": 10.5, "next_step": "Pay EMI by 5th",
                     "last_updated": "2024-01-01"}]
        if "customer_id" in cypher and "$cid" in cypher and "Claim" in cypher:
            return []
        if "phone" in cypher or "email" in cypher:
            return [{"customer_id": "CUST-001", "email": "customer@example.com",
                     "phone": "+919999999999", "city": "Mumbai"}]
        return []

    def write(self, cypher, params=None):
        pass

    def close(self):
        pass

    enabled = True


class EmptyNeo4j:
    """Active Neo4j test double with no matching customer graph data."""

    def query(self, cypher, params=None):
        return []

    def write(self, cypher, params=None):
        pass

    def close(self):
        pass

    enabled = True


class WorkbookNeo4j:
    """Neo4j test double backed by the same XLSX rows used by the graph loader."""

    enabled = True

    def __init__(self):
        import openpyxl

        workbook = openpyxl.load_workbook("data/bfsi.xlsx", data_only=True)
        self.customers = self._rows(workbook["Customer_data"])
        self.loans = self._rows(workbook["Loan_Processing_data"])
        self.claims = self._rows(workbook["Claim_data"])

    @staticmethod
    def _rows(sheet):
        headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
        return [dict(zip(headers, row)) for row in sheet.iter_rows(min_row=2, values_only=True)]

    def query(self, cypher, params=None):
        params = params or {}
        if "MATCH (c:Customer)" in cypher:
            identifiers = {str(params.get("id", "")), str(params.get("stripped", ""))}
            for row in self.customers:
                values = {
                    str(row.get("Phone") or ""),
                    str(row.get("PrimaryEmail") or ""),
                    str(row.get("SecondaryEmail") or ""),
                }
                if identifiers & values:
                    return [{
                        "customer_id": str(row["CustomerID"]),
                        "email": str(row.get("PrimaryEmail") or ""),
                        "phone": str(row.get("Phone") or ""),
                        "city": str(row.get("City") or ""),
                        "registration_date": str(row.get("RegistrationDate") or ""),
                    }]
            return []

        customer_id = str(params.get("cid", ""))
        if "HAS_LOAN" in cypher:
            return [{
                "loan_id": str(row["LoanID"]),
                "loan_type": str(row["LoanType"]),
                "status": str(row["LoanStatus"]),
                "amount_inr": row["LoanAmount (INR)"],
                "interest_rate": row["InterestRate (%)"],
                "next_step": str(row["NextStep"]),
                "last_updated": str(row["LastUpdatedDate"]),
            } for row in self.loans if str(row["CustomerID"]) == customer_id]
        if "HAS_CLAIM" in cypher:
            return [{
                "claim_id": str(row["ClaimID"]),
                "policy_type": str(row["PolicyType"]),
                "claim_type": str(row["ClaimType"]),
                "status": str(row["ClaimStatus"]),
                "amount_claimed": row["AmountClaimed (INR)"],
                "amount_approved": row["AmountApproved (INR)"],
                "reason": str(row["ReasonForStatus"]),
                "last_updated": str(row["LastUpdatedDate"]),
            } for row in self.claims if str(row["CustomerID"]) == customer_id]
        return []

    def write(self, cypher, params=None):
        pass

    def close(self):
        pass


class Recorder:
    def __init__(self):
        self.sent = []

    def send_text(self, *args):
        self.sent.append(args)
        return {"id": "provider-message-id"}


_DEFAULT_TEST_NEO4J = object()


def graph(repository, whatsapp=None, email=None, crm=None, neo4j_client=_DEFAULT_TEST_NEO4J):
    if neo4j_client is _DEFAULT_TEST_NEO4J:
        neo4j_client = EmptyNeo4j()
    return OrchestrationGraph(
        repository,
        agent=CXAgent(NoLLM()),
        rag=FakeRAG(),
        delivery=OutboundDeliveryService(whatsapp=whatsapp, email=email),
        crm=crm,
        neo4j_client=neo4j_client,
    )


def whatsapp_message(message_id="wamid-1", text="What is my loan EMI status?", metadata=None):
    return WhatsAppAdapter().normalize(
        WhatsAppWebhookPayload(
            from_="+919999999999",
            text=text,
            message_id=message_id,
            metadata={"provider": "whatsapp_cloud", **(metadata or {})},
        )
    )


def email_message(message_id="email-1", body="What is my loan EMI status?", metadata=None):
    return EmailAdapter().normalize(
        EmailWebhookPayload(
            from_email="customer@example.com",
            subject="Loan query",
            body=body,
            message_id=message_id,
            metadata={"provider": "email_webhook", **(metadata or {})},
        )
    )


# ── Core workflow tests ───────────────────────────────────────────────────────

def test_whatsapp_bfsi_query_resolves_with_citation_and_sends_reply():
    repo = SQLiteCXRepository(":memory:")
    sender = Recorder()
    response = graph(repo, whatsapp=sender).run(whatsapp_message())
    assert response.resolved is False
    assert response.next_best_action == "answer_delivered"
    assert response.citations[0]["source"] == "InboxIQ_BFSI_KB.pdf:p3"
    assert response.outbound_status == "sent"
    assert sender.sent
    ticket_step = next(entry for entry in response.workflow_trace if entry["step"] == "create_or_update_ticket")
    assert ticket_step["details"]["skipped"] is True
    evidence = repo.list_retrieval_evidence()
    assert evidence[0]["source"] == "InboxIQ_BFSI_KB.pdf:p3"


def test_email_complaint_escalates_and_sends_reply():
    repo = SQLiteCXRepository(":memory:")
    sender = Recorder()
    response = graph(repo, email=sender).run(
        email_message(body="This is an unacceptable complaint. I need a human agent immediately.")
    )
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
    workflow.run(whatsapp_message(message_id="wamid-2", text="Can you check my EMI again?"))
    conversation = repo.get_conversation(response.conversation_id)
    assert len(conversation["turns"]) == 4
    assert "EMI" in conversation["summary"]


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


def test_whatsapp_cloud_webhook_e2e_preserves_channel_and_sends_reply(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.routes import webhooks

    repo = SQLiteCXRepository(":memory:")
    sender = Recorder()
    router = OmnichannelRouter(graph(repo, whatsapp=sender))
    monkeypatch.setattr(webhooks, "get_router", lambda: router)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "e2e-whatsapp-secret")

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [
                                {"wa_id": "918555870077", "profile": {"name": "Phase 1 Tester"}}
                            ],
                            "messages": [
                                {
                                    "from": "918555870077",
                                    "id": "wamid-e2e-kyc",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "How can I update my KYC?"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(b"e2e-whatsapp-secret", body, hashlib.sha256).hexdigest()

    response = TestClient(app).post(
        "/integrations/whatsapp/webhook",
        content=body,
        headers={"x-hub-signature-256": signature, "content-type": "application/json"},
    )

    assert response.status_code == 202
    result = response.json()["messages"][0]
    assert response.json()["messages_received"] == 1
    assert result["outbound_status"] == "sent"
    assert result["workflow_trace"][0]["step"] == "receive_message"
    assert sender.sent[0][0] == "918555870077"

    conversation = repo.get_conversation(result["conversation_id"])
    assert [turn["channel"] for turn in conversation["turns"]] == ["whatsapp", "whatsapp"]
    assert conversation["turns"][0]["external_message_id"] == "wamid-e2e-kyc"
    assert conversation["turns"][1]["delivery_status"] == "sent"


def test_email_webhook_e2e_preserves_channel_creates_ticket_and_sends_reply(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.routes import webhooks

    repo = SQLiteCXRepository(":memory:")
    sender = Recorder()
    router = OmnichannelRouter(graph(repo, email=sender))
    monkeypatch.setattr(webhooks, "get_router", lambda: router)
    monkeypatch.setenv("EMAIL_WEBHOOK_SECRET", "e2e-email-secret")

    response = TestClient(app).post(
        "/integrations/email/webhook",
        json={
            "from_email": "customer@example.com",
            "subject": "Loan support",
            "body": "What is the status of my loan LN001? Please connect me to a human agent.",
            "message_id": "email-e2e-human-agent",
            "metadata": {"source": "phase1-e2e"},
        },
        headers={"x-email-webhook-secret": "e2e-email-secret"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["outbound_status"] == "sent"
    assert result["ticket_id"]
    assert result["next_best_action"] == "human_follow_up"
    assert sender.sent[0][0] == "customer@example.com"

    conversation = repo.get_conversation(result["conversation_id"])
    assert [turn["channel"] for turn in conversation["turns"]] == ["email", "email"]
    assert conversation["turns"][0]["external_message_id"] == "email-e2e-human-agent"
    assert conversation["turns"][1]["ticket_id"] == result["ticket_id"]


# ── BFSI intent classification tests ─────────────────────────────────────────

def test_intent_classifier_supports_bfsi_intents():
    assert classify_intent("Please report a fraud transaction on my account").intent == Intent.FRAUD_REPORT
    assert classify_intent("What is my outstanding loan EMI?").intent == Intent.LOAN_STATUS
    assert classify_intent("I want to speak to a human representative").intent == Intent.HUMAN_ESCALATION
    assert classify_intent("Block my lost credit card immediately").intent == Intent.CARD_MANAGEMENT
    assert classify_intent("I need to file an insurance claim for my accident").intent == Intent.INSURANCE_CLAIM
    assert classify_intent("What is the status of my existing claim?").intent == Intent.CLAIM_STATUS
    assert classify_intent("How do I apply for a home loan?").intent == Intent.LOAN_APPLICATION


def test_llm_intent_result_accepts_model_reason():
    result = CXAgent(ValidLLM()).analyze("What is the status of my loan repayment?")
    assert result.intent == Intent.LOAN_STATUS
    assert result.reason == "Customer asked about their loan repayment status."
    assert result.analysis_source == "groq_llm"


def test_llm_intent_guardrails_raise_understated_sentiment_and_urgency():
    result = CXAgent(UnderstatedLLM()).analyze(
        "Someone hacked my account and stole all my money. This is fraud! Help immediately!"
    )
    assert result.intent == Intent.FRAUD_REPORT
    assert result.sentiment == "negative"
    assert result.urgency.value == "high"
    assert "Deterministic guardrails raised: sentiment, urgency." in result.reason


# ── Neo4j enrichment tests ────────────────────────────────────────────────────

def test_neo4j_context_enriches_intent_classification():
    repo = SQLiteCXRepository(":memory:")
    fake_neo4j = FakeNeo4j()
    response = graph(repo, neo4j_client=fake_neo4j).run(
        whatsapp_message(text="What is my loan status?")
    )
    assert response.intent in {
        "loan_status", "general_inquiry", "loan_application", "loan_default_notice"
    }


def test_query_resolution_agent_routes_transactional_intent_to_neo4j():
    from services.agent_service.orchestration_agents import QueryResolutionAgent
    from services.channel_service.adapters.whatsapp_adapter import WhatsAppAdapter
    from shared.schemas.messages import WhatsAppWebhookPayload

    agent = QueryResolutionAgent(neo4j_client=FakeNeo4j())
    msg = WhatsAppAdapter().normalize(
        WhatsAppWebhookPayload(from_="+919999999999", text="What is my loan status?",
                               message_id="test-1", metadata={"provider": "test"})
    )
    context = {"graph_context": {"customer_id": "CUST-001"}}
    resolution = agent.run(msg, context, intent="loan_status")
    assert resolution.retrieval_backend == "neo4j_graph"
    assert "loan" in resolution.answer.lower() or "L001" in resolution.answer


def test_query_resolution_agent_routes_general_inquiry_to_rag():
    from services.agent_service.orchestration_agents import QueryResolutionAgent
    from services.channel_service.adapters.whatsapp_adapter import WhatsAppAdapter
    from shared.schemas.messages import WhatsAppWebhookPayload

    fake_rag = FakeRAG()
    agent = QueryResolutionAgent(rag=fake_rag, neo4j_client=FakeNeo4j())
    msg = WhatsAppAdapter().normalize(
        WhatsAppWebhookPayload(from_="+919999999999", text="What documents do I need for KYC?",
                               message_id="test-2", metadata={"provider": "test"})
    )
    resolution = agent.run(msg, {}, intent="kyc_update")
    # kyc_update is not a TRANSACTIONAL_INTENT → should use RAG
    assert resolution.retrieval_backend != "neo4j_graph"


def test_process_intents_never_route_to_customer_graph():
    from services.agent_service.orchestration_agents import QueryResolutionAgent

    fake_rag = FakeRAG()
    agent = QueryResolutionAgent(rag=fake_rag, neo4j_client=FakeNeo4j())
    context = {"graph_context": {"customer_id": "CUST-001"}}

    claim = agent.run(
        whatsapp_message(text="How do I file a health insurance claim?"),
        context,
        intent=Intent.INSURANCE_CLAIM.value,
    )
    loan = agent.run(
        whatsapp_message(text="How do I apply for a home loan?"),
        context,
        intent=Intent.LOAN_APPLICATION.value,
    )

    assert claim.retrieval_backend != "neo4j_graph"
    assert loan.retrieval_backend != "neo4j_graph"


def test_five_question_kb_and_graph_e2e_matrix():
    class EmptyStore:
        def similarity_search(self, query, k):
            return []

    class NoGeneration:
        model = "test"

        def generate_answer(self, query, contexts, conversation_context):
            return {"text": "", "model": self.model, "llm_used": False}

    rag = RAGPipeline(store=EmptyStore(), generator=NoGeneration())
    neo4j = WorkbookNeo4j()

    cases = [
        {
            "message": WhatsAppAdapter().normalize(WhatsAppWebhookPayload(
                from_="917700920746",
                text="How do I file a health insurance claim?",
                message_id="matrix-kb-health-claim",
                metadata={"provider": "test"},
            )),
            "intent": Intent.INSURANCE_CLAIM.value,
            "backend": "keyword_fallback",
            "source_page": ":p2",
            "expected": ("cashless", "reimbursement"),
            "forbidden": "No insurance claims",
        },
        {
            "message": EmailAdapter().normalize(EmailWebhookPayload(
                from_email="digvijayyadav48@gmail.com",
                subject="Home loan application",
                body="How do I apply for a home loan?",
                message_id="matrix-kb-home-loan",
                metadata={"provider": "test"},
            )),
            "intent": Intent.LOAN_APPLICATION.value,
            "backend": "keyword_fallback",
            "source_page": ":p1",
            "expected": ("application form", "property documents"),
            "forbidden": "No active loan",
        },
        {
            "message": WhatsAppAdapter().normalize(WhatsAppWebhookPayload(
                from_="917700920746",
                text="How do I report a lost or stolen credit card?",
                message_id="matrix-kb-lost-card",
                metadata={"provider": "test"},
            )),
            "intent": Intent.CARD_MANAGEMENT.value,
            "backend": "keyword_fallback",
            "source_page": ":p1",
            "expected": ("block", "replacement"),
            "forbidden": "No active",
        },
        {
            "message": WhatsAppAdapter().normalize(WhatsAppWebhookPayload(
                from_="919876510100",
                text="What is the status of my home loan application?",
                message_id="matrix-graph-loan-status",
                metadata={"provider": "test"},
            )),
            "intent": Intent.LOAN_STATUS.value,
            "backend": "neo4j_graph",
            "source_page": None,
            "expected": ("LN001", "LN016", "Under Review"),
            "forbidden": "application form",
        },
        {
            "message": EmailAdapter().normalize(EmailWebhookPayload(
                from_email="fathima.devasahayam@ganitinc.com",
                subject="Claim status",
                body="What is the status of my existing insurance claim?",
                message_id="matrix-graph-claim-status",
                metadata={"provider": "test"},
            )),
            "intent": Intent.CLAIM_STATUS.value,
            "backend": "neo4j_graph",
            "source_page": None,
            "expected": ("CLM001", "CLM016", "Under Review"),
            "forbidden": "cashless claims",
        },
    ]

    for case in cases:
        repository = SQLiteCXRepository(":memory:")
        sender = Recorder()
        delivery = (
            OutboundDeliveryService(whatsapp=sender)
            if case["message"].channel.value == "whatsapp"
            else OutboundDeliveryService(email=sender)
        )
        workflow = OrchestrationGraph(
            repository,
            agent=CXAgent(NoLLM()),
            rag=rag,
            delivery=delivery,
            neo4j_client=neo4j,
        )
        response = workflow.run(case["message"])

        assert response.intent == case["intent"]
        assert response.retrieval_backend == case["backend"]
        assert all(text.lower() in response.message.lower() for text in case["expected"])
        assert case["forbidden"].lower() not in response.message.lower()
        assert response.outbound_status == "sent"
        assert sender.sent
        if case["source_page"]:
            assert response.citations
            assert case["source_page"] in response.citations[0]["source"]
        else:
            assert response.citations[0]["source"] == "neo4j_customer_graph"


# ── RAG / knowledge base tests ────────────────────────────────────────────────

def test_low_confidence_retrieval_creates_ticket():
    repo = SQLiteCXRepository(":memory:")
    response = graph(repo).run(whatsapp_message(text="unknown question xyz"))
    assert response.ticket_id
    assert repo.get_ticket(response.ticket_id)


def test_distinct_bfsi_issues_create_distinct_team_tickets():
    repo = SQLiteCXRepository(":memory:")
    workflow = graph(repo)

    kyc_response = workflow.run(
        whatsapp_message(
            message_id="distinct-team-kyc",
            text="My KYC update documents are still not accepted, this is urgent.",
        )
    )
    claim_response = workflow.run(
        whatsapp_message(
            message_id="distinct-team-claim",
            text="I need to file a hospitalization reimbursement claim urgently.",
        )
    )

    kyc_ticket = repo.get_ticket(kyc_response.ticket_id)
    claim_ticket = repo.get_ticket(claim_response.ticket_id)

    assert kyc_ticket["ticket_id"] != claim_ticket["ticket_id"]
    assert kyc_ticket["intent"] == "kyc_update"
    assert kyc_ticket["assigned_team"] == "compliance"
    assert claim_ticket["intent"] == "insurance_claim"
    assert claim_ticket["assigned_team"] == "claims"
    assert "claims team" in claim_response.message.lower()


def test_customer_answer_kb_documents_are_knowledge_base_type():
    """PDF KB docs should all have doc_type=knowledge_base."""
    documents = load_knowledge_documents()
    assert documents
    assert {document.metadata["doc_type"] for document in documents} == {"knowledge_base"}
    assert all(document.metadata["source"].split(":p", 1)[0].endswith(".pdf") for document in documents)


def test_rag_discards_non_kb_contexts_before_generation():
    class UnsafeStore:
        def similarity_search(self, query, k):
            return [
                {
                    "text": "Customer: Example Name | Loan: L123",
                    "score": 0.99,
                    "metadata": {"source": "ticket-export.json", "doc_type": "ticket_history"},
                },
                {
                    "text": "Insurance claim process requires form IC-01.",
                    "score": 0.8,
                    "metadata": {"source": "InboxIQ_BFSI_KB.pdf:p5", "doc_type": "knowledge_base"},
                },
            ]

    class ContextRecorder:
        def generate_answer(self, query, contexts, conversation_context):
            assert [c["metadata"]["source"] for c in contexts] == ["InboxIQ_BFSI_KB.pdf:p5"]
            return {"text": "Approved answer.", "llm_used": True}

    answer = RAGPipeline(store=UnsafeStore(), generator=ContextRecorder()).answer("insurance claim process")
    assert [c["metadata"]["source"] for c in answer["contexts"]] == ["InboxIQ_BFSI_KB.pdf:p5"]


def test_rag_uses_pdf_keyword_fallback_when_vector_store_is_empty():
    class EmptyStore:
        def similarity_search(self, query, k):
            return []

    class NoGeneration:
        def generate_answer(self, query, contexts, conversation_context):
            return {"text": "", "model": "test", "llm_used": False}

    answer = RAGPipeline(store=EmptyStore(), generator=NoGeneration()).answer("credit card block")
    assert answer["contexts"]
    assert answer["retrieval_backend"] == "keyword_fallback"
    assert answer["citations"][0]["source"].startswith("InboxIQ_BFSI_KB.pdf")


# ── Security / auth tests ─────────────────────────────────────────────────────

def test_rag_reranks_stolen_card_pdf_faq_above_weak_vector_hit():
    class WeakVectorStore:
        def similarity_search(self, query, k):
            return [{
                "text": "BFSI Knowledge Base FAQs Banking Services Q: How can I open a new savings account?",
                "score": 0.5,
                "metadata": {"source": "InboxIQ_BFSI_KB.pdf:p1", "doc_type": "knowledge_base"},
            }]

    class ContextRecorder:
        def generate_answer(self, query, contexts, conversation_context):
            assert "lost or stolen" in contexts[0]["text"].lower()
            assert "block your card" in contexts[0]["text"].lower()
            return {
                "text": "Block the card immediately through the hotline, mobile app, or internet banking. [1]",
                "model": "test",
                "llm_used": True,
            }

    answer = RAGPipeline(store=WeakVectorStore(), generator=ContextRecorder()).answer(
        "what should I do, my card is stolen"
    )
    assert answer["retrieval_backend"] == "hybrid_keyword_rerank"
    assert "lost or stolen" in answer["contexts"][0]["text"].lower()


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

    assert webhook.status_code == 202
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
                "external_ticket_id": "BFSI-101",
                "external_ticket_url": "https://your-domain.atlassian.net/browse/BFSI-101",
            },
        )

    def add_comment(self, external_ticket_id, comment):
        assert external_ticket_id == "BFSI-101"
        return CRMResult("synced", {"comment_id": "comment-1"})

    def update_ticket_status(self, external_ticket_id, status):
        assert external_ticket_id == "BFSI-101"
        return CRMResult("synced", {"status": status})


def test_invalid_crm_url_is_recorded_without_raising(monkeypatch):
    from services.crm_service.client import CRMClient

    monkeypatch.setenv("CRM_PROVIDER", "jira")
    monkeypatch.setenv("CRM_BASE_URL", "Log in with Atlassian account")
    monkeypatch.setenv("CRM_API_TOKEN", "token")
    monkeypatch.setenv("CRM_USER_EMAIL", "support@example.com")
    monkeypatch.setenv("CRM_PROJECT_KEY", "SUP")

    result = CRMClient()._request("GET", "/rest/api/3/myself")

    assert result.status == "failed"
    assert "invalid URL" in result.error


def test_invalid_crm_url_does_not_block_whatsapp_reply(monkeypatch):
    monkeypatch.setenv("CRM_PROVIDER", "jira")
    monkeypatch.setenv("CRM_BASE_URL", "Log in with Atlassian account")
    monkeypatch.setenv("CRM_API_TOKEN", "token")
    monkeypatch.setenv("CRM_USER_EMAIL", "support@example.com")
    monkeypatch.setenv("CRM_PROJECT_KEY", "SUP")

    repo = SQLiteCXRepository(":memory:")
    sender = Recorder()
    response = graph(repo, whatsapp=sender).run(
        whatsapp_message(message_id="crm-failure-reply", text="unknown question xyz")
    )

    assert response.outbound_status == "sent"
    assert sender.sent
    ticket = repo.get_ticket(response.ticket_id)
    assert ticket["crm_sync_status"] == "failed"
    assert "invalid URL" in ticket["crm_sync_error"]


def test_ticket_jira_sync_and_lifecycle():
    repo = SQLiteCXRepository(":memory:")
    workflow = graph(repo, crm=FakeCRM())
    response = workflow.run(
        email_message(body="This is a terrible complaint. The service is unacceptable and I am extremely frustrated.")
    )
    ticket = repo.get_ticket(response.ticket_id)
    assert ticket["external_ticket_id"] == "BFSI-101"
    assert "atlassian.net" in ticket["external_ticket_url"]
    assert ticket["crm_sync_status"] == "synced"
    assert ticket["sla_due_at"]
    assert ticket["escalation_reason"].startswith("manual_review_required")

    manager = workflow.tickets
    comment = manager.add_comment(response.ticket_id, "Escalated to fraud team.")
    assert comment["details"]["crm_sync_status"] == "synced"
    updated = manager.update_status(response.ticket_id, TicketStatus.IN_PROGRESS)
    assert updated["status"] == "in_progress"
    assert [event["event_type"] for event in repo.list_ticket_events(response.ticket_id)] == [
        "ticket_created",
        "crm_sync_synced",
        "comment_added",
        "status_updated",
    ]


# ── Admin / infrastructure tests ──────────────────────────────────────────────

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
    assert len(response.json()["agents"]) == 3
    assert response.json()["agents"][0]["name"] == "intent_classification_agent"
    assert "groq" in response.json()["agents"][0]["execution"]


def test_hashing_embeddings_are_an_explicit_fallback(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "hashing")
    embeddings = SemanticEmbeddings()
    assert embeddings.status()["active_backend"] == "hashing_fallback"
    assert len(embeddings.embed_query("What is my loan balance?")) == 384
