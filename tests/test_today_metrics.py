"""GET /analytics/today - the console's day: AI vs human reply volume, per-person handling,
and open cases where the customer was unhappy with a person's reply.

Built on a real migrated SQLite file (not mocks), so the SQL and the turn-metadata parsing
are what is under test. No LLM is involved anywhere in this path."""

import json
from datetime import datetime, timedelta, timezone

from services.analytics_service.aggregator import get_today_metrics
from services.persistence_service.repository import SQLiteCXRepository

NOW = datetime.now(timezone.utc)


def _at(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat()


def _db(tmp_path):
    path = str(tmp_path / "today.db")
    repo = SQLiteCXRepository(path)
    return path, repo


def _seed(repo, conv="conv_1", cust="cust_1"):
    with repo.connection() as conn:
        conn.execute("INSERT OR IGNORE INTO customers(customer_id, display_name, metadata_json, created_at, updated_at) "
                     "VALUES (?, 'Test Customer', '{}', ?, ?)", (cust, _at(600), _at(600)))
        conn.execute("INSERT INTO conversations(conversation_id, customer_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
                     (conv, cust, _at(600), _at(1)))


def _ticket(repo, tid, conv="conv_1", cust="cust_1", status="open", created=120, sla_in=60, first_response=None):
    with repo.connection() as conn:
        conn.execute(
            "INSERT INTO tickets(ticket_id, conversation_id, customer_id, title, description, intent, priority, "
            "assigned_team, status, created_at, updated_at, sla_due_at, first_response_at) "
            "VALUES (?, ?, ?, 'Case', 'desc', 'complaint', 'high', 'customer_care', ?, ?, ?, ?, ?)",
            (tid, conv, cust, status, _at(created), _at(created),
             (NOW - timedelta(minutes=created) + timedelta(minutes=sla_in)).isoformat(),
             _at(first_response) if first_response is not None else None),
        )


def _turn(repo, tid_turn, direction, minutes_ago, text="hi", ticket="tkt_1", channel="email",
          conv="conv_1", cust="cust_1", **meta):
    with repo.connection() as conn:
        conn.execute(
            "INSERT INTO conversation_turns(turn_id, conversation_id, customer_id, channel, direction, text, "
            "ticket_id, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tid_turn, conv, cust, channel, direction, text, ticket, json.dumps(meta), _at(minutes_ago)),
        )


def test_ai_and_human_replies_are_counted_separately_and_holding_lines_are_neither(tmp_path):
    path, repo = _db(tmp_path)
    _seed(repo)
    _ticket(repo, "tkt_1")
    _turn(repo, "t1", "inbound", 30)
    _turn(repo, "t2", "outbound", 29, text="Support Agent will help you with this shortly ...")
    _turn(repo, "t3", "outbound", 20, text="Here is your balance")                       # AI
    _turn(repo, "t4", "outbound", 10, source="agent_composed_reply", actor="neha")      # human
    _turn(repo, "t5", "outbound", 5, channel="whatsapp", source="manual_agent_reply", actor="neha")
    _turn(repo, "t6", "outbound", 60 * 30, text="yesterday's AI answer")               # before today

    v = get_today_metrics(path, NOW - timedelta(hours=2))["volume"]

    assert v["ai"] == 1
    assert v["human"] == 2
    assert v["inbound"] == 1
    assert v["by_channel"]["email"] == {"ai": 1, "human": 1}
    assert v["by_channel"]["whatsapp"] == {"ai": 0, "human": 1}


def test_per_person_handling_counts_channels_drafts_sla_and_mood_after(tmp_path):
    path, repo = _db(tmp_path)
    since = NOW - timedelta(hours=3)
    _seed(repo)
    _ticket(repo, "tkt_1", created=100, sla_in=60, first_response=50)   # answered inside SLA
    _turn(repo, "t1", "inbound", 100)
    _turn(repo, "t2", "outbound", 50, source="manual_agent_reply", actor="neha")
    _turn(repo, "t3", "inbound", 40, sentiment="positive")
    with repo.connection() as conn:
        conn.execute("INSERT INTO reply_drafts(draft_id, conversation_id, customer_id, ticket_id, channel, draft_text, "
                     "status, sent_text, decided_by, decided_at, created_at) "
                     "VALUES ('d1','conv_1','cust_1','tkt_1','email','Same text','sent','Same text','neha',?,?)",
                     (_at(50), _at(99)))

    rows = {a["actor"]: a for a in get_today_metrics(path, since)["agents"]}

    neha = rows["neha"]
    assert neha["replies"] == 1
    assert neha["by_channel"] == {"email": 1}
    assert neha["drafts_sent_as_is"] == 1 and neha["drafts_edited"] == 0
    assert neha["sla_total"] == 1 and neha["sla_met"] == 1
    assert neha["median_first_reply_minutes"] == 50.0
    assert neha["mood_after"]["positive"] == 1


def test_attention_flags_an_unhappy_reaction_to_a_human_reply_until_someone_replies(tmp_path):
    path, repo = _db(tmp_path)
    since = NOW - timedelta(hours=3)
    _seed(repo)
    _ticket(repo, "tkt_1", status="in_progress", first_response=50)
    _turn(repo, "t1", "inbound", 100)
    _turn(repo, "t2", "outbound", 50, source="manual_agent_reply", actor="neha")
    _turn(repo, "t3", "inbound", 20, text="This is useless, still not fixed", sentiment="negative")

    attention = get_today_metrics(path, since)["attention"]
    assert [a["ticket_id"] for a in attention] == ["tkt_1"]
    assert attention[0]["replied_by"] == "neha"
    assert "still not fixed" in attention[0]["customer_said"]

    # a person answers the complaint: it is no longer waiting on anyone
    _turn(repo, "t4", "outbound", 5, source="agent_composed_reply", actor="neha")
    assert get_today_metrics(path, since)["attention"] == []


def test_attention_ignores_negative_messages_nobody_has_answered_yet_and_closed_cases(tmp_path):
    path, repo = _db(tmp_path)
    since = NOW - timedelta(hours=3)
    _seed(repo)
    _ticket(repo, "tkt_1", status="open")
    # angry, but no person has replied - that is an ordinary "To reply" case, not a reaction
    _turn(repo, "t1", "inbound", 30, sentiment="negative")
    assert get_today_metrics(path, since)["attention"] == []

    _seed(repo, conv="conv_2", cust="cust_2")
    _ticket(repo, "tkt_2", conv="conv_2", cust="cust_2", status="closed")
    _turn(repo, "u1", "outbound", 50, conv="conv_2", cust="cust_2", ticket="tkt_2", source="manual_agent_reply", actor="neha")
    _turn(repo, "u2", "inbound", 40, conv="conv_2", cust="cust_2", ticket="tkt_2", sentiment="negative")
    assert get_today_metrics(path, since)["attention"] == []


def test_composer_replies_count_as_human_contacts(tmp_path):
    path, repo = _db(tmp_path)
    _seed(repo)
    _ticket(repo, "tkt_1")
    _turn(repo, "t1", "outbound", 5, source="agent_composed_reply", actor="neha")
    contacts = repo.list_ticket_contacts()["tkt_1"]
    assert contacts[0]["by_human"] is True
