"""Tests for the cross-sell/up-sell opportunity engine + approve→offer-draft flow.

The LLM is never called: gates/candidates/validation are pure functions, and the
pipeline tests inject a fake generator. Delivery is exercised in log mode.
"""

from datetime import datetime, timedelta, timezone

from services.agent_assist_service import opportunity_engine as oe
from services.persistence_service.repository import SQLiteCXRepository
from shared.schemas.messages import Channel, InboundMessage


def _days_from_now(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")


_HEALTHY_CONTEXT = {
    "loans": [{"loan_id": "L1", "amount_inr": 500000}],
    "policies": [],
    "credit_cards": [],
    "accounts": [{"avg_monthly_balance": 180000, "min_balance_required": 10000}],
    "fixed_deposits": [{"fd_id": "FD1", "principal_amount": 500000,
                        "maturity_date": _days_from_now(40)}],
}


# ── Gates (reference-doc essence only: open ticket + latest sentiment;
#     fraud/dpd and attrition gates were dropped by user decision) ───────────

def _gates(**overrides):
    args = dict(tickets=[], turns=[])
    args.update(overrides)
    return oe.check_gates(**args)


def test_gates_pass_for_healthy_customer():
    assert _gates() is None


def test_gate_open_ticket_does_not_suppress():
    # Open-ticket gate dropped (user decision): the admin reviewing each offer
    # is the judgment layer; only sentiment gates.
    assert _gates(tickets=[{"status": "open"}]) is None


def test_gate_negative_sentiment_suppresses():
    turns = [{"direction": "inbound", "metadata": {"sentiment": "negative"}, "text": "bad"}]
    assert _gates(turns=turns) == "recent negative sentiment"


def test_gate_only_latest_inbound_sentiment_counts():
    turns = [
        {"direction": "inbound", "metadata": {"sentiment": "negative"}, "text": "bad"},
        {"direction": "inbound", "metadata": {"sentiment": "positive"}, "text": "thanks!"},
    ]
    assert _gates(turns=turns) is None


def test_gate_fraud_or_dpd_does_not_suppress():
    # Dropped gates: card state never suppresses (only ticket + sentiment do).
    result = oe.generate_opportunities(
        generator=_FakeGenerator("[]"), customer={},
        graph_context={**_HEALTHY_CONTEXT, "credit_cards": [{"dpd": 45, "fraud_flag": True}]},
        tickets=[], turns=[], already_suggested=[],
    )
    assert "suppressed" not in result


# ── Candidate set ───────────────────────────────────────────────────────────

def _products(ctx):
    return {c["product"]: c for c in oe.build_candidates(ctx)}


def test_candidates_loan_without_life_cover():
    cands = _products(_HEALTHY_CONTEXT)
    assert "term_insurance" in cands
    assert cands["term_insurance"]["kind"] == "cross_sell"


def test_candidates_no_term_offer_when_already_insured():
    ctx = {**_HEALTHY_CONTEXT, "policies": [{"policy_type": "Term Insurance"}]}
    assert "term_insurance" not in _products(ctx)


def test_candidates_fd_renewal_when_maturity_near():
    cands = _products(_HEALTHY_CONTEXT)
    assert "fd_renewal" in cands
    assert cands["fd_renewal"]["kind"] == "up_sell"
    assert "matures in" in cands["fd_renewal"]["basis"]


def test_candidates_no_fd_renewal_when_maturity_far():
    ctx = {**_HEALTHY_CONTEXT,
           "fixed_deposits": [{"principal_amount": 500000, "maturity_date": _days_from_now(200)}]}
    assert "fd_renewal" not in _products(ctx)


def test_candidates_fixed_deposit_gap_for_high_balance_without_fd():
    ctx = {**_HEALTHY_CONTEXT, "fixed_deposits": []}
    cands = _products(ctx)
    assert "fixed_deposit" in cands
    assert cands["fixed_deposit"]["kind"] == "cross_sell"


def test_candidates_premium_tier_for_high_balance():
    assert "premium_account_tier" in _products(_HEALTHY_CONTEXT)


def test_candidates_credit_card_gap():
    cands = _products(_HEALTHY_CONTEXT)
    assert "credit_card" in cands


def test_candidates_premium_card_for_hni_on_entry_variant():
    ctx = {**_HEALTHY_CONTEXT,
           "credit_cards": [{"card_variant": "Classic", "credit_limit": 1065000, "dpd": 0,
                             "reward_points_balance": 994}]}
    cands = {c["product"]: c for c in oe.build_candidates(ctx, segment="HNI")}
    assert "premium_card_upgrade" in cands
    assert "HNI customer on a Classic card" in cands["premium_card_upgrade"]["basis"]


def test_candidates_no_premium_card_for_hni_when_seriously_overdue():
    # Rule 8 keeps the dpd guard (user choice "a"): dpd >= 30 = wrong premise.
    ctx = {**_HEALTHY_CONTEXT,
           "credit_cards": [{"card_variant": "Classic", "credit_limit": 1065000, "dpd": 45}]}
    assert "premium_card_upgrade" not in {c["product"] for c in oe.build_candidates(ctx, segment="HNI")}


def test_candidates_no_premium_card_for_regular_segment():
    ctx = {**_HEALTHY_CONTEXT,
           "credit_cards": [{"card_variant": "Classic", "credit_limit": 100000, "dpd": 0}]}
    assert "premium_card_upgrade" not in {c["product"] for c in oe.build_candidates(ctx, segment="Retail")}


def test_candidates_one_per_product_when_two_rules_fire():
    # Points rule + segment rule both propose premium_card_upgrade → one candidate.
    ctx = {**_HEALTHY_CONTEXT,
           "credit_cards": [{"card_variant": "Classic", "credit_limit": 1065000, "dpd": 0,
                             "reward_points_balance": 9000}]}
    products = [c["product"] for c in oe.build_candidates(ctx, segment="HNI")]
    assert products.count("premium_card_upgrade") == 1


def test_candidates_empty_for_no_holdings():
    empty = {"loans": [], "policies": [], "credit_cards": [], "accounts": [], "fixed_deposits": []}
    products = set(_products(empty))
    # Only the "no health policy" gap can fire without any holdings.
    assert products <= {"health_insurance"}


# ── Rule 9: charge-waiver upgrade ───────────────────────────────────────────

def test_candidates_charge_waiver_for_repeated_unreversed_charges():
    charges = [
        {"charge_type": "min_balance", "amount": 265, "reversal_status": "none"},
        {"charge_type": "min_balance", "amount": 265, "reversal_status": ""},
    ]
    cands = {c["product"]: c for c in oe.build_candidates(_HEALTHY_CONTEXT, charges=charges)}
    assert "charge_waiver_account_upgrade" in cands
    assert "INR 530" in cands["charge_waiver_account_upgrade"]["basis"]


def test_candidates_no_charge_waiver_for_single_or_reversed_charges():
    single = [{"charge_type": "min_balance", "amount": 265, "reversal_status": "none"}]
    assert "charge_waiver_account_upgrade" not in {
        c["product"] for c in oe.build_candidates(_HEALTHY_CONTEXT, charges=single)}
    reversed_charges = [
        {"charge_type": "min_balance", "amount": 265, "reversal_status": "Reversed"},
        {"charge_type": "late_fee", "amount": 500, "reversal_status": "approved"},
    ]
    assert "charge_waiver_account_upgrade" not in {
        c["product"] for c in oe.build_candidates(_HEALTHY_CONTEXT, charges=reversed_charges)}


# ── Rule 10: asked-about-product ────────────────────────────────────────────

def test_candidates_interest_fires_for_loan_question_without_loans():
    ctx = {**_HEALTHY_CONTEXT, "loans": []}
    turns = [{"direction": "inbound", "intent": "loan_application",
              "created_at": "2026-07-23T10:00:00", "text": "loan rates?"}]
    cands = {c["product"]: c for c in oe.build_candidates(ctx, turns=turns)}
    assert "personal_loan_info" in cands
    assert "asked about loans" in cands["personal_loan_info"]["basis"]


def test_candidates_interest_does_not_fire_when_product_held():
    # Has loans → a loan question is servicing, not interest in a new product.
    turns = [{"direction": "inbound", "intent": "loan_status", "text": "my loan?"}]
    assert "personal_loan_info" not in {
        c["product"] for c in oe.build_candidates(_HEALTHY_CONTEXT, turns=turns)}


def test_candidates_interest_ignores_unmapped_intents():
    # general_inquiry has no product family (taxonomy limitation) → never fires.
    ctx = {**_HEALTHY_CONTEXT, "loans": []}
    turns = [{"direction": "inbound", "intent": "general_inquiry", "text": "FD rates?"}]
    assert "personal_loan_info" not in {
        c["product"] for c in oe.build_candidates(ctx, turns=turns)}


# ── LLM output validation (never trust the LLM) ─────────────────────────────

_CANDS = [
    {"product": "fd_renewal", "kind": "up_sell", "basis": "FD of INR 500,000 matures in 40 days"},
    {"product": "term_insurance", "kind": "cross_sell", "basis": "loan with no cover"},
]


def test_parse_valid_output():
    raw = ('[{"product": "fd_renewal", "kind": "up_sell", '
           '"pitch": "Your INR 500,000 FD matures in 40 days - renew to lock the rate.", '
           '"reason": "asked about FD maturity", "confidence": 0.8}]')
    out = oe.parse_and_validate(raw, _CANDS)
    assert len(out) == 1
    assert out[0]["product"] == "fd_renewal"
    assert out[0]["confidence"] == 0.8


def test_parse_drops_invented_product():
    raw = ('[{"product": "personal_loan", "kind": "cross_sell", "pitch": "Take a loan!", '
           '"confidence": 0.9}]')
    assert oe.parse_and_validate(raw, _CANDS) == []


def test_parse_kind_comes_from_candidate_not_llm():
    raw = ('[{"product": "fd_renewal", "kind": "cross_sell", "pitch": "Renew your INR 500,000 FD.", '
           '"confidence": 0.7}]')
    out = oe.parse_and_validate(raw, _CANDS)
    assert out[0]["kind"] == "up_sell"  # our definition wins over the LLM's claim


def test_parse_survives_markdown_wrapping():
    raw = ('Here you go:\n```json\n[{"product": "term_insurance", "pitch": "Cover your loan.", '
           '"confidence": 0.6}]\n```')
    out = oe.parse_and_validate(raw, _CANDS)
    assert len(out) == 1


def test_parse_garbage_returns_empty():
    assert oe.parse_and_validate("sorry, I cannot help with that", _CANDS) == []
    assert oe.parse_and_validate("", _CANDS) == []


def test_parse_caps_at_max():
    raw = ('[{"product": "fd_renewal", "pitch": "a", "confidence": 0.9},'
           '{"product": "term_insurance", "pitch": "b", "confidence": 0.8},'
           '{"product": "fd_renewal", "pitch": "c", "confidence": 0.7}]')
    assert len(oe.parse_and_validate(raw, _CANDS)) == oe.MAX_OPPORTUNITIES


# ── Full pipeline with a fake generator ─────────────────────────────────────

class _FakeGenerator:
    def __init__(self, text: str, llm_used: bool = True):
        self._text = text
        self._llm_used = llm_used
        self.calls = []

    def _generate(self, system_prompt, user_prompt, operation="", metadata=None):
        self.calls.append(user_prompt)
        return {"text": self._text, "llm_used": self._llm_used}


def test_pipeline_suppressed_makes_no_llm_call():
    gen = _FakeGenerator("[]")
    turns = [{"direction": "inbound", "metadata": {"sentiment": "negative"}, "text": "bad"}]
    result = oe.generate_opportunities(
        generator=gen, customer={}, graph_context=_HEALTHY_CONTEXT,
        tickets=[], turns=turns, already_suggested=[],
    )
    assert result == {"suppressed": "recent negative sentiment"}
    assert gen.calls == []


def test_pipeline_returns_validated_opportunities():
    gen = _FakeGenerator(
        '[{"product": "fd_renewal", "pitch": "Renew your INR 500,000 FD before it matures.", '
        '"reason": "maturity near", "confidence": 0.8}]')
    result = oe.generate_opportunities(
        generator=gen, customer={"name": "Test", "registration_date": "2020-01-01"},
        graph_context=_HEALTHY_CONTEXT, tickets=[], turns=[],
        already_suggested=[],
    )
    assert result["opportunities"][0]["product"] == "fd_renewal"
    # Candidate list + do-not-repeat section made it into the prompt.
    assert "fd_renewal" in gen.calls[0]
    assert "ALREADY SUGGESTED" in gen.calls[0]


def test_pipeline_llm_failure_returns_empty_not_crash():
    gen = _FakeGenerator("", llm_used=False)
    result = oe.generate_opportunities(
        generator=gen, customer={"registration_date": "2020-01-01"},
        graph_context=_HEALTHY_CONTEXT, tickets=[], turns=[],
        already_suggested=[],
    )
    assert result["opportunities"] == []


# ── Approve → offer draft → dual-channel send (route level) ─────────────────

def _seed_customer(repo: SQLiteCXRepository):
    # linked_email makes resolve_customer store an email channel identity too,
    # giving the customer both push channels (whatsapp + email) on record.
    message = InboundMessage(
        channel=Channel.WHATSAPP, channel_identifier="+919999900001",
        text="hello", provider="test", correlation_id="corr-opp",
        metadata={"linked_email": "opp-test@example.com"},
    )
    customer = repo.resolve_customer(message)
    conv = repo.get_or_create_conversation(customer["customer_id"])
    return customer, conv


def test_approve_offer_creates_draft_and_send_delivers_to_both_channels(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.routes import agent_assist, reply_drafts

    monkeypatch.setenv("ADMIN_API_KEY", "opp-test-key")
    monkeypatch.setenv("OUTBOUND_DELIVERY_MODE", "log")
    repo = SQLiteCXRepository(":memory:")
    customer, conv = _seed_customer(repo)
    rec = repo.add_agent_assist_recommendation(
        conversation_id=conv["conversation_id"], customer_id=customer["customer_id"],
        ticket_id=None, action_type="up_sell",
        reason="Your INR 500,000 FD matures in 40 days - renew to lock the rate.",
        confidence=0.8, priority=5,
        metadata={"product": "fd_renewal", "source": "opportunity_engine"},
    )
    monkeypatch.setattr(agent_assist, "get_repository", lambda: repo)
    monkeypatch.setattr(reply_drafts, "get_repository", lambda: repo)

    client = TestClient(app)
    headers = {"x-admin-key": "opp-test-key"}

    # Approve → draft created.
    decision = client.post(
        f"/admin/agent-assist/recommendations/{rec['recommendation_id']}/decision",
        json={"status": "approved"}, headers=headers,
    )
    assert decision.status_code == 200
    draft_id = decision.json().get("draft_id")
    assert draft_id
    draft = repo.get_reply_draft(draft_id)
    assert draft["channel"] == "offer"
    assert "FD matures" in draft["draft_text"]

    # A second offer approval is blocked while a draft is pending.
    rec2 = repo.add_agent_assist_recommendation(
        conversation_id=conv["conversation_id"], customer_id=customer["customer_id"],
        ticket_id=None, action_type="cross_sell", reason="Another offer",
        confidence=0.5, priority=5, metadata={"product": "term_insurance"},
    )
    blocked = client.post(
        f"/admin/agent-assist/recommendations/{rec2['recommendation_id']}/decision",
        json={"status": "approved"}, headers=headers,
    )
    assert blocked.status_code == 409
    # ...and the blocked recommendation is still pending (untouched).
    assert repo.get_agent_assist_recommendation(rec2["recommendation_id"])["status"] == "pending"

    # Send → one delivery + one outbound turn per push channel.
    sent = client.post(
        f"/admin/reply-drafts/{draft_id}/send",
        json={"text": "Final offer text with the INR 500,000 FD details."}, headers=headers,
    )
    assert sent.status_code == 200
    body = sent.json()
    channels = {d["channel"] for d in body["deliveries"]}
    assert channels == {"whatsapp", "email"}
    assert len(body["turn_ids"]) == 2
    turns = repo.list_recent_turns(conv["conversation_id"])
    offer_turns = [t for t in turns if (t.get("metadata") or {}).get("source") == "opportunity_offer"]
    assert {t["channel"] for t in offer_turns} == {"whatsapp", "email"}
    assert repo.get_reply_draft(draft_id)["status"] == "sent"
    audit = repo.list_audit_events()
    assert any(e["event_type"] == "offer_draft_sent" for e in audit)


def test_approve_offer_fails_without_push_channel(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.routes import agent_assist

    monkeypatch.setenv("ADMIN_API_KEY", "opp-test-key-2")
    repo = SQLiteCXRepository(":memory:")
    # Web-chat-only customer: no whatsapp/email identity on record.
    message = InboundMessage(
        channel=Channel.WEB_CHAT, channel_identifier="web_session:opp-user",
        text="hello", provider="web_portal", correlation_id="corr-opp-2",
    )
    customer = repo.resolve_customer(message)
    conv = repo.get_or_create_conversation(customer["customer_id"])
    rec = repo.add_agent_assist_recommendation(
        conversation_id=conv["conversation_id"], customer_id=customer["customer_id"],
        ticket_id=None, action_type="cross_sell", reason="Offer",
        confidence=0.5, priority=5, metadata={"product": "health_insurance"},
    )
    monkeypatch.setattr(agent_assist, "get_repository", lambda: repo)

    client = TestClient(app)
    response = client.post(
        f"/admin/agent-assist/recommendations/{rec['recommendation_id']}/decision",
        json={"status": "approved"}, headers={"x-admin-key": "opp-test-key-2"},
    )
    assert response.status_code == 400
    # Recommendation untouched; no draft created.
    assert repo.get_agent_assist_recommendation(rec["recommendation_id"])["status"] == "pending"
    assert repo.list_reply_drafts(conversation_id=conv["conversation_id"]) == []


def test_dismiss_offer_does_not_create_draft(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.routes import agent_assist

    monkeypatch.setenv("ADMIN_API_KEY", "opp-test-key-3")
    repo = SQLiteCXRepository(":memory:")
    customer, conv = _seed_customer(repo)
    rec = repo.add_agent_assist_recommendation(
        conversation_id=conv["conversation_id"], customer_id=customer["customer_id"],
        ticket_id=None, action_type="up_sell", reason="Offer",
        confidence=0.5, priority=5, metadata={"product": "fd_renewal"},
    )
    monkeypatch.setattr(agent_assist, "get_repository", lambda: repo)

    client = TestClient(app)
    response = client.post(
        f"/admin/agent-assist/recommendations/{rec['recommendation_id']}/decision",
        json={"status": "dismissed"}, headers={"x-admin-key": "opp-test-key-3"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"
    assert repo.list_reply_drafts(conversation_id=conv["conversation_id"]) == []
