from datetime import datetime, timedelta, timezone

from services.agent_assist_service.next_best_action import NextBestActionEngine
from services.persistence_service.repository import SQLiteCXRepository
from shared.schemas.agent_assist import ActionType
from shared.schemas.messages import Channel, InboundMessage
from shared.schemas.responses import ChannelResponse
from shared.schemas.tickets import Ticket, TicketPriority, TicketStatus
from shared.utils.ids import new_id


def _make_customer(repo: SQLiteCXRepository, identifier: str = "+919999999999") -> str:
    """Create a real customer row (conversations has a FK on customer_id)."""
    message = InboundMessage(
        channel=Channel.WHATSAPP,
        channel_identifier=identifier,
        text="hello",
        provider="test",
        correlation_id="corr-setup",
    )
    return repo.resolve_customer(message)["customer_id"]


def _ticket(priority=TicketPriority.HIGH, status=TicketStatus.OPEN, intent="complaint",
            sla_hours_remaining=1, age_hours=3) -> dict:
    now = datetime.now(timezone.utc)
    created = now - timedelta(hours=age_hours)
    ticket = Ticket(
        ticket_id=new_id("tkt"),
        conversation_id="conv-1",
        customer_id="cust-1",
        title="Test ticket",
        description="Test",
        intent=intent,
        priority=priority,
        assigned_team="customer_care",
        status=status,
        sla_due_at=now + timedelta(hours=sla_hours_remaining),
        created_at=created,
    )
    return ticket.model_dump(mode="json")


# ── Rule provider unit tests (no LLM, no Neo4j) ────────────────────────────

def test_escalate_rule_fires_when_high_priority_ticket_nearing_sla():
    ticket = _ticket(priority=TicketPriority.HIGH, sla_hours_remaining=1, age_hours=3)  # 1/4 window left
    action = NextBestActionEngine._rule_escalate_aging_high_priority(ticket)
    assert action is not None
    assert action.action_type == ActionType.ESCALATE_TO_SENIOR


def test_escalate_rule_does_not_fire_for_medium_priority():
    ticket = _ticket(priority=TicketPriority.MEDIUM, sla_hours_remaining=1, age_hours=3)
    assert NextBestActionEngine._rule_escalate_aging_high_priority(ticket) is None


def test_escalate_rule_does_not_fire_when_plenty_of_sla_time_left():
    ticket = _ticket(priority=TicketPriority.CRITICAL, sla_hours_remaining=10, age_hours=1)
    assert NextBestActionEngine._rule_escalate_aging_high_priority(ticket) is None


def test_escalate_rule_none_when_no_ticket():
    assert NextBestActionEngine._rule_escalate_aging_high_priority(None) is None


def test_negative_sentiment_streak_rule_fires_after_two_consecutive():
    turns = [
        {"direction": "inbound", "metadata": {"sentiment": "negative"}},
        {"direction": "outbound", "metadata": {}},
        {"direction": "inbound", "metadata": {"sentiment": "negative"}},
    ]
    action = NextBestActionEngine._rule_repeat_negative_sentiment(turns)
    assert action is not None
    assert action.action_type == ActionType.OFFER_RETENTION


def test_negative_sentiment_streak_rule_does_not_fire_on_single_negative():
    turns = [{"direction": "inbound", "metadata": {"sentiment": "negative"}}]
    assert NextBestActionEngine._rule_repeat_negative_sentiment(turns) is None


def test_kyc_rule_fires_for_open_kyc_ticket():
    ticket = _ticket(intent="kyc_update", status=TicketStatus.OPEN)
    action = NextBestActionEngine._rule_kyc_pending(ticket)
    assert action is not None
    assert action.action_type == ActionType.REQUEST_DOCUMENT


def test_kyc_rule_does_not_fire_for_resolved_ticket():
    ticket = _ticket(intent="kyc_update", status=TicketStatus.CLOSED)
    assert NextBestActionEngine._rule_kyc_pending(ticket) is None


# ── Cross-sell/up-sell moved to opportunity_engine (see test_opportunities.py) ──


# ── Engine + persistence integration ────────────────────────────────────────

class _FakeNeo4jForGraphContext:
    """Keyed by Neo4j-side graph_customer_id ('CRN...'), never by the SQLite customer_id —
    this is what caught the real bug: _load_graph_context() must resolve through the
    customer's stored channel identity, not assume the two id spaces coincide."""

    enabled = True

    def query(self, cypher, params=None):
        params = params or {}
        if "MATCH (c:Customer)" in cypher:
            if params.get("id") == "919999900000" or params.get("stripped") == "9999900000":
                return [{"customer_id": "CRN00099999", "email": None, "phone": "919999900000", "city": "Pune"}]
            return []
        # queries.get_all_customer_records walks every relationship in ONE query and returns
        # `label` + `props`, so the old per-relationship branches (HAS_LOAN / HAS_POLICY /
        # HAS_CLAIM appearing in the Cypher) no longer match anything.
        if "properties(n)" in cypher:
            return [{"label": "Loan", "parent_policy_type": None, "props": {
                "loan_id": "L1", "loan_type": "Personal Loan", "status": "Active",
                "amount_inr": 100000, "interest_rate": 10.0,
            }}]
        return []

    def write(self, cypher, params=None):
        pass

    def close(self):
        pass


def test_load_graph_context_resolves_via_channel_identity_not_sqlite_customer_id():
    """Regression test: SQLite customer_id (e.g. 'cust_82804...') and the Neo4j BFSI graph's
    customer_id (e.g. 'CRN00010004') are independently generated and never coincide. Passing
    the SQLite id straight into get_customer_context_by_id silently returns {} — which made
    cross-sell (and every other graph-context-dependent rule) permanently dead for any
    non-portal channel. This caught a real bug found while smoke-testing before a demo."""
    repo = SQLiteCXRepository(":memory:")
    message = InboundMessage(
        channel=Channel.WHATSAPP,
        channel_identifier="919999900000",
        text="hello",
        provider="test",
        correlation_id="corr-1",
    )
    customer = repo.resolve_customer(message)
    engine = NextBestActionEngine(repo, neo4j_client=_FakeNeo4jForGraphContext())

    ctx = engine._load_graph_context(customer["customer_id"])

    assert ctx.get("customer_id") == "CRN00099999"
    assert ctx.get("loans")


def test_engine_recommend_persists_nothing_by_itself_and_returns_action_set():
    """The engine is pure — it computes recommendations but does not persist them.
    Persistence + dedupe happens in the route layer (apps/api/routes/agent_assist.py)."""
    repo = SQLiteCXRepository(":memory:")
    customer_id = _make_customer(repo)
    conv = repo.get_or_create_conversation(customer_id)
    repo.append_turn(
        conversation_id=conv["conversation_id"], customer_id=customer_id, channel="whatsapp",
        direction="inbound", text="This is unacceptable", intent="complaint", urgency="high",
        metadata={"sentiment": "negative"},
    )
    repo.append_turn(
        conversation_id=conv["conversation_id"], customer_id=customer_id, channel="whatsapp",
        direction="inbound", text="Still nothing has happened", intent="complaint", urgency="high",
        metadata={"sentiment": "negative"},
    )
    engine = NextBestActionEngine(repo, neo4j_client=None)
    result = engine.recommend(conv["conversation_id"])
    assert result.customer_id == customer_id
    assert any(a.action_type == ActionType.OFFER_RETENTION for a in result.actions)


def test_route_persists_and_dedupes_recommendations(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.routes import agent_assist

    monkeypatch.setenv("ADMIN_API_KEY", "agent-assist-test-key")
    repo = SQLiteCXRepository(":memory:")
    customer_id = _make_customer(repo)
    conv = repo.get_or_create_conversation(customer_id)
    repo.append_turn(
        conversation_id=conv["conversation_id"], customer_id=customer_id, channel="whatsapp",
        direction="inbound", text="This is unacceptable", intent="complaint", urgency="high",
        metadata={"sentiment": "negative"},
    )
    repo.append_turn(
        conversation_id=conv["conversation_id"], customer_id=customer_id, channel="whatsapp",
        direction="inbound", text="Still nothing has happened", intent="complaint", urgency="high",
        metadata={"sentiment": "negative"},
    )
    monkeypatch.setattr(agent_assist, "get_repository", lambda: repo)
    monkeypatch.setattr(agent_assist, "_try_neo4j", lambda: None)

    client = TestClient(app)
    headers = {"x-admin-key": "agent-assist-test-key"}

    first = client.get(
        "/admin/agent-assist/next-best-actions",
        params={"conversation_id": conv["conversation_id"]},
        headers=headers,
    )
    assert first.status_code == 200
    actions = first.json()["actions"]
    assert actions
    rec_id = actions[0]["recommendation_id"]

    # Calling again must not create duplicate pending rows for the same action_type.
    second = client.get(
        "/admin/agent-assist/next-best-actions",
        params={"conversation_id": conv["conversation_id"]},
        headers=headers,
    )
    assert len(second.json()["actions"]) == len(actions)

    decision = client.post(
        f"/admin/agent-assist/recommendations/{rec_id}/decision",
        json={"status": "approved"},
        headers=headers,
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"

    audit = repo.list_audit_events()
    assert any(e["event_type"] == "nba_recommendation_approved" for e in audit)


def test_agent_assist_routes_require_admin_key(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import app

    monkeypatch.setenv("ADMIN_API_KEY", "agent-assist-test-key-2")
    client = TestClient(app)
    response = client.get("/admin/agent-assist/next-best-actions", params={"conversation_id": "conv-x"})
    assert response.status_code == 401


# ── ChannelResponse.workflow_status regression (naming-collision rename) ───

def test_channel_response_validates_with_workflow_status_field():
    response = ChannelResponse(
        correlation_id="corr-1",
        conversation_id="conv-1",
        customer_id="cust-1",
        message="hello",
        resolved=False,
        intent="complaint",
        sentiment="negative",
        urgency="high",
        confidence=0.9,
        workflow_status="human_follow_up",
    )
    assert response.workflow_status == "human_follow_up"
    assert "next_best_action" not in response.model_dump()
