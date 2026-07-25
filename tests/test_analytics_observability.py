"""Tests for Session-9 analytics + observability work (all offline — zero Groq calls):

- LLM config version tag (_normalize_params / _config_version): changes when a param changes,
  deterministic, decodable.
- Solution-performance aggregator: escalation-rate denominator = inbound turns; risk/critical/
  drafts; risk-band + merged escalation-reason breakdowns.
- Channel metrics: no fake 'graph'/'portal' channels, counted per real ticket channel.
"""
import sqlite3

from services.observability_service.llm_usage import _config_version, _normalize_params


# ── version tag ───────────────────────────────────────────────────────────────
def test_config_version_changes_when_a_param_changes():
    a = _normalize_params("llama-3.1-8b-instant", {"temperature": 0.2})
    b = _normalize_params("llama-3.1-8b-instant", {"temperature": 0.5})
    assert _config_version(a) != _config_version(b)


def test_config_version_changes_when_a_param_is_added():
    a = _normalize_params("llama-3.1-8b-instant", {"temperature": 0.2})
    b = _normalize_params("llama-3.1-8b-instant", {"temperature": 0.2, "max_tokens": 512})
    assert _config_version(a) != _config_version(b)


def test_config_version_is_deterministic_and_tagged():
    a = _normalize_params("m", {"temperature": 0.2})
    again = _normalize_params("m", {"temperature": 0.2})
    v = _config_version(a)
    assert v == _config_version(again)
    assert v.startswith("v-") and len(v) == 6


def test_normalize_params_none_passthrough_keeps_old_call_sites():
    # No params supplied -> None, so record_llm_call falls back to the provider fingerprint.
    assert _normalize_params("m", None) is None


def test_normalize_params_only_includes_what_was_sent():
    cfg = _normalize_params("m", {"temperature": 0.2, "top_p": None})
    assert cfg == {"model": "m", "temperature": 0.2}  # top_p None dropped


# ── DB fixtures for aggregator tests ──────────────────────────────────────────
def _seed(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE conversations(conversation_id TEXT PRIMARY KEY, customer_id TEXT, status TEXT);
        CREATE TABLE conversation_turns(turn_id TEXT PRIMARY KEY, conversation_id TEXT,
            customer_id TEXT, channel TEXT, direction TEXT, text TEXT, ticket_id TEXT);
        CREATE TABLE tickets(ticket_id TEXT PRIMARY KEY, conversation_id TEXT, customer_id TEXT,
            priority TEXT, status TEXT, escalation_reason TEXT, priority_score REAL,
            created_at TEXT, updated_at TEXT);
        CREATE TABLE reply_drafts(draft_id TEXT PRIMARY KEY, status TEXT);
        CREATE TABLE channel_identities(customer_id TEXT, channel TEXT);
        """
    )
    # 1 customer, 3 inbound queries across web_chat + whatsapp, plus outbound replies carrying ticket ids
    conn.execute("INSERT INTO conversations VALUES('c1','cust1','active')")
    turns = [
        ("t1", "c1", "cust1", "web_chat", "inbound", "hi", None),
        ("t2", "c1", "cust1", "web_chat", "outbound", "reply", "tk1"),
        ("t3", "c1", "cust1", "whatsapp", "inbound", "help", None),
        ("t4", "c1", "cust1", "whatsapp", "outbound", "reply", "tk2"),
        ("t5", "c1", "cust1", "web_chat", "inbound", "again", None),
    ]
    conn.executemany("INSERT INTO conversation_turns VALUES(?,?,?,?,?,?,?)", turns)
    # tk1 escalated critical (open), tk2 escalated medium (open)
    conn.execute("INSERT INTO tickets VALUES('tk1','c1','cust1','critical','open',"
                 "'assisted_resolution_required:transaction_dispute',90,'2026-07-25','2026-07-25')")
    conn.execute("INSERT INTO tickets VALUES('tk2','c1','cust1','medium','open',"
                 "'assisted_resolution_required:loan_status',30,'2026-07-25','2026-07-25')")
    conn.executemany("INSERT INTO reply_drafts VALUES(?,?)", [("d1", "sent"), ("d2", "sent"), ("d3", "pending")])
    # channel_identities intentionally includes fake internal channels
    conn.executemany("INSERT INTO channel_identities VALUES(?,?)",
                     [("cust1", "web_chat"), ("cust1", "whatsapp"), ("cust1", "graph"), ("cust1", "portal")])
    conn.commit()
    conn.close()


def test_solution_performance_escalation_uses_inbound_turns(tmp_path):
    from services.analytics_service.aggregator import get_solution_performance
    db = str(tmp_path / "t.db")
    _seed(db)
    sp = get_solution_performance(db)
    # 2 escalated tickets / 3 inbound turns = 66.7%
    assert sp.escalations == 2
    assert sp.inbound_queries == 3
    assert sp.escalation_rate_pct == round(2 / 3 * 100, 1)
    assert sp.critical_open == 1
    assert sp.drafts_handled == 2
    assert sp.avg_risk_score == 60.0  # (90+30)/2


def test_solution_performance_merges_escalation_reasons(tmp_path):
    from services.analytics_service.aggregator import get_solution_performance
    db = str(tmp_path / "t.db")
    _seed(db)
    sp = get_solution_performance(db)
    # both raw reasons prettify to "Assisted resolution" -> ONE merged bar of count 2
    reasons = {r.label: r.count for r in sp.by_escalation_reason}
    assert reasons == {"Assisted resolution": 2}


def test_channel_metrics_excludes_fake_internal_channels(tmp_path):
    from services.analytics_service.aggregator import get_channel_metrics
    db = str(tmp_path / "t.db")
    _seed(db)
    channels = {c.channel for c in get_channel_metrics(db).channels}
    assert "graph" not in channels
    assert "portal" not in channels
    assert channels == {"web_chat", "whatsapp"}  # only real message channels
