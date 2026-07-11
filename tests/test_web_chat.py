from services.agent_service.cx_agent import CXAgent
from services.channel_service.adapters.web_chat_adapter import WebChatAdapter
from services.channel_service.delivery import OutboundDeliveryService
from services.orchestration_service.graph import OrchestrationGraph
from services.persistence_service.repository import SQLiteCXRepository
from shared.schemas.messages import Channel, WebChatWebhookPayload


class EmptyNeo4j:
    """Active Neo4j test double with no matching customer graph data."""

    enabled = True

    def query(self, cypher, params=None):
        return []

    def write(self, cypher, params=None):
        pass

    def close(self):
        pass


class FakeResolutionEngine:
    def __init__(self, level="L1"):
        self.level = level

    def resolve_query_level(self, query, intent, sentiment):
        return {
            "intent": intent,
            "sentiment": sentiment,
            "resolution_level": self.level,
            "confidence": 0.9,
            "reason": "Test stub decision.",
        }


class FakeRAG:
    def answer(self, query, context):
        return {
            "answer": "You can check your loan repayment schedule in the app.",
            "confidence": 0.91,
            "contexts": [],
            "citations": [],
            "llm": {"llm_used": False},
        }


class ValidLoanStatusLLM:
    """Returns an account-specific intent with high confidence."""
    def classify_message(self, message, context):
        return {
            "intent": "loan_status",
            "confidence": 0.9,
            "urgency": "low",
            "sentiment": "neutral",
            "reason": "Customer asked about their loan repayment status.",
        }


class GeneralInquiryLLM:
    def classify_message(self, message, context):
        return {
            "intent": "general_inquiry",
            "confidence": 0.9,
            "urgency": "low",
            "sentiment": "positive",
            "reason": "Customer asked a general question.",
        }


def web_chat_message(session_id="session-1", text="Hello, I have a question."):
    return WebChatAdapter().normalize(
        WebChatWebhookPayload(session_id=session_id, text=text, metadata={"provider": "test"})
    )


def build_graph(llm=None, repository=None):
    repo = repository or SQLiteCXRepository(":memory:")
    return OrchestrationGraph(
        repo,
        agent=CXAgent(llm or GeneralInquiryLLM()),
        rag=FakeRAG(),
        delivery=OutboundDeliveryService(),
        neo4j_client=EmptyNeo4j(),
        resolution_engine=FakeResolutionEngine(),
    ), repo


def test_web_chat_message_creates_conversation_and_returns_synchronous_reply():
    workflow, _ = build_graph()
    response = workflow.run(web_chat_message())
    assert response.message
    assert response.conversation_id
    assert response.customer_id
    assert response.outbound_status == "sent"


def test_anonymous_web_session_blocked_from_account_specific_query():
    """Anonymous web visitors (no phone/email match in the BFSI customer graph) must be
    rejected before any account data is returned — same compliance gate WhatsApp/Email use."""
    workflow, _ = build_graph(llm=ValidLoanStatusLLM())
    response = workflow.run(web_chat_message(text="What is my loan status?"))
    assert response.workflow_status == "customer_validation_required"
    assert response.intent == "customer_not_registered"
    assert "registered" in response.message.lower()


def test_same_session_id_reuses_customer_and_conversation():
    workflow, repo = build_graph()
    first = workflow.run(web_chat_message(session_id="session-42", text="Hi there"))
    second = workflow.run(web_chat_message(session_id="session-42", text="Following up on my question"))
    assert first.customer_id == second.customer_id
    assert first.conversation_id == second.conversation_id


def test_different_session_ids_get_different_customers():
    workflow, _ = build_graph()
    first = workflow.run(web_chat_message(session_id="session-a"))
    second = workflow.run(web_chat_message(session_id="session-b"))
    assert first.customer_id != second.customer_id


def test_delivery_send_never_invokes_email_connector_for_web_chat():
    class ExplodingEmail:
        def send_text(self, *args, **kwargs):
            raise AssertionError("email connector must never be called for web_chat")

    delivery = OutboundDeliveryService(email=ExplodingEmail())
    message = web_chat_message()
    result = delivery.send(message, "Reply text")
    assert result["status"] == "sent"
    assert result["provider"] == "web_chat_sync"


def test_web_chat_channel_identifier_is_isolated_from_whatsapp_and_email():
    message = web_chat_message(session_id="abc123")
    assert message.channel == Channel.WEB_CHAT
    assert message.channel_identifier == "web_session:abc123"
