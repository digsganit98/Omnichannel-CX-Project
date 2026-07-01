import sqlite3
from datetime import datetime, timedelta, timezone

from .metrics import (
    AgentMetrics,
    ChannelCount,
    ChannelMetrics,
    IntentCount,
    IntentMetrics,
    OverviewMetrics,
    RealtimeEvent,
    SentimentMetrics,
    TicketTrendPoint,
)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_overview(db_path: str) -> OverviewMetrics:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN status NOT IN ('resolved','closed') THEN 1 ELSE 0 END) AS open_cnt,
                SUM(CASE WHEN status IN ('resolved','closed') THEN 1 ELSE 0 END) AS resolved_cnt,
                SUM(CASE WHEN escalation_reason IS NOT NULL AND escalation_reason != '' THEN 1 ELSE 0 END) AS escalated_cnt,
                SUM(CASE WHEN sla_due_at IS NOT NULL AND sla_due_at < datetime('now')
                              AND status NOT IN ('resolved','closed') THEN 1 ELSE 0 END) AS sla_breach_cnt
            FROM tickets
            """
        ).fetchone()

        avg_row = conn.execute(
            """
            SELECT AVG(
                (julianday(updated_at) - julianday(created_at)) * 1440
            ) AS avg_mins
            FROM tickets
            WHERE status IN ('resolved','closed')
            """
        ).fetchone()

        conv_cnt = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        cust_cnt = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]

        # Matches inbox page logic: use stored metadata sentiment first (set by the AI
        # classifier), fall back to keyword detection only when no sentiment was stored.
        # Keywords match the NEG_KW list used by clientSentiment() in the inbox JS.
        _neg_cond = """(
            LOWER(metadata_json) LIKE '%"sentiment":"negative"%'
            OR LOWER(metadata_json) LIKE '%"sentiment": "negative"%'
            OR (
                LOWER(metadata_json) NOT LIKE '%"sentiment":%'
                AND (
                    LOWER(text) LIKE '%angry%'
                    OR LOWER(text) LIKE '%bad%'
                    OR LOWER(text) LIKE '%terrible%'
                    OR LOWER(text) LIKE '%frustrated%'
                    OR LOWER(text) LIKE '%late%'
                    OR LOWER(text) LIKE '%failed%'
                    OR LOWER(text) LIKE '%problem%'
                    OR LOWER(text) LIKE '%damaged%'
                    OR LOWER(text) LIKE '%not received%'
                    OR LOWER(text) LIKE '%not credited%'
                    OR LOWER(text) LIKE '%charged twice%'
                    OR LOWER(text) LIKE '%cancel%'
                    OR LOWER(text) LIKE '%fraud%'
                    OR LOWER(text) LIKE '%stolen%'
                    OR LOWER(text) LIKE '%unauthorized%'
                    OR LOWER(text) LIKE '%incorrect charge%'
                    OR LOWER(text) LIKE '%overdue%'
                    OR LOWER(text) LIKE '%default%'
                    OR LOWER(text) LIKE '%claim rejected%'
                    OR LOWER(text) LIKE '%policy lapsed%'
                    OR LOWER(text) LIKE '%blocked account%'
                    OR LOWER(text) LIKE '%money gone%'
                    OR LOWER(text) LIKE '%wrong transfer%'
                    OR LOWER(text) LIKE '%human agent%'
                    OR LOWER(text) LIKE '%human representative%'
                )
            )
        )"""

        sent_row = conn.execute(
            f"""
            SELECT
                SUM(CASE WHEN created_at >= datetime('now', '-24 hours')
                             AND {_neg_cond}
                         THEN 1 ELSE 0 END) AS today_neg,
                SUM(CASE WHEN created_at >= datetime('now', '-24 hours')
                         THEN 1 ELSE 0 END) AS today_total,
                SUM(CASE WHEN created_at >= datetime('now', '-48 hours')
                             AND created_at < datetime('now', '-24 hours')
                             AND {_neg_cond}
                         THEN 1 ELSE 0 END) AS yest_neg,
                SUM(CASE WHEN created_at >= datetime('now', '-48 hours')
                             AND created_at < datetime('now', '-24 hours')
                         THEN 1 ELSE 0 END) AS yest_total
            FROM conversation_turns
            WHERE direction = 'inbound'
            """
        ).fetchone()

        def _pct(neg, total):
            return round(neg * 100.0 / total, 1) if total else 0.0

        today_neg_pct = _pct(sent_row["today_neg"] or 0, sent_row["today_total"] or 0)
        yest_neg_pct = _pct(sent_row["yest_neg"] or 0, sent_row["yest_total"] or 0)

        frt_row = conn.execute(
            """
            SELECT
                AVG(CASE WHEN first_out IS NOT NULL AND first_out > first_in
                         THEN (julianday(first_out) - julianday(first_in)) * 1440
                    END) AS avg_recent,
                AVG(CASE WHEN first_out IS NOT NULL AND first_out > first_in
                             AND first_in < datetime('now', '-7 days')
                         THEN (julianday(first_out) - julianday(first_in)) * 1440
                    END) AS avg_older
            FROM (
                SELECT
                    MIN(CASE WHEN direction = 'inbound'  THEN created_at END) AS first_in,
                    MIN(CASE WHEN direction = 'outbound' THEN created_at END) AS first_out
                FROM conversation_turns
                GROUP BY conversation_id
            )
            """
        ).fetchone()

        avg_frt = round(frt_row["avg_recent"] or 0, 1)
        avg_frt_old = round(frt_row["avg_older"] or 0, 1)

    return OverviewMetrics(
        total_open=row["open_cnt"] or 0,
        total_resolved=row["resolved_cnt"] or 0,
        total_escalated=row["escalated_cnt"] or 0,
        avg_resolution_minutes=round(avg_row["avg_mins"] or 0, 1),
        sla_breach_count=row["sla_breach_cnt"] or 0,
        total_conversations=conv_cnt or 0,
        total_customers=cust_cnt or 0,
        neg_sentiment_today_pct=today_neg_pct,
        neg_sentiment_yesterday_pct=yest_neg_pct,
        avg_first_response_minutes=avg_frt,
        avg_first_response_last_week_minutes=avg_frt_old,
    )


def get_channel_metrics(db_path: str) -> ChannelMetrics:
    with _connect(db_path) as conn:
        ticket_rows = conn.execute(
            """
            SELECT ci.channel, COUNT(*) AS cnt
            FROM tickets t
            JOIN conversations c ON t.conversation_id = c.conversation_id
            JOIN channel_identities ci ON c.customer_id = ci.customer_id
            GROUP BY ci.channel
            """
        ).fetchall()

        msg_rows = conn.execute(
            "SELECT channel, COUNT(*) AS cnt FROM conversation_turns GROUP BY channel"
        ).fetchall()

    ticket_map = {r["channel"]: r["cnt"] for r in ticket_rows}
    msg_map = {r["channel"]: r["cnt"] for r in msg_rows}
    all_channels = set(ticket_map) | set(msg_map)

    channels = [
        ChannelCount(
            channel=ch,
            ticket_count=ticket_map.get(ch, 0),
            message_count=msg_map.get(ch, 0),
        )
        for ch in sorted(all_channels)
    ]
    return ChannelMetrics(channels=channels)


def get_intent_metrics(db_path: str, top_n: int = 10) -> IntentMetrics:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT intent, COUNT(*) AS cnt
            FROM conversation_turns
            WHERE intent IS NOT NULL AND intent != ''
            GROUP BY intent
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (top_n,),
        ).fetchall()

    return IntentMetrics(intents=[IntentCount(intent=r["intent"], count=r["cnt"]) for r in rows])


def get_sentiment_metrics(db_path: str) -> SentimentMetrics:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                SUM(CASE WHEN LOWER(metadata_json) LIKE '%"sentiment":"positive"%'
                             OR LOWER(metadata_json) LIKE '%"sentiment": "positive"%'
                         THEN 1 ELSE 0 END) AS pos,
                SUM(CASE WHEN LOWER(metadata_json) LIKE '%"sentiment":"negative"%'
                             OR LOWER(metadata_json) LIKE '%"sentiment": "negative"%'
                         THEN 1 ELSE 0 END) AS neg,
                COUNT(*) AS total
            FROM conversation_turns
            WHERE direction = 'inbound'
            """
        ).fetchone()

    pos = rows["pos"] or 0
    neg = rows["neg"] or 0
    total = rows["total"] or 0
    neutral = max(0, total - pos - neg)
    return SentimentMetrics(positive=pos, negative=neg, neutral=neutral, total=total)


def get_agent_metrics(db_path: str) -> list[AgentMetrics]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                assigned_team AS agent,
                COUNT(*) AS handled,
                AVG((julianday(updated_at) - julianday(created_at)) * 1440) AS avg_mins,
                SUM(CASE WHEN escalation_reason IS NOT NULL AND escalation_reason != '' THEN 1 ELSE 0 END) AS escalations
            FROM tickets
            GROUP BY assigned_team
            ORDER BY handled DESC
            """
        ).fetchall()

    return [
        AgentMetrics(
            agent=r["agent"],
            handled=r["handled"],
            avg_handle_minutes=round(r["avg_mins"] or 0, 1),
            escalations=r["escalations"] or 0,
        )
        for r in rows
    ]


def get_ticket_trend(db_path: str, days: int = 14) -> list[TicketTrendPoint]:
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    with _connect(db_path) as conn:
        created_rows = conn.execute(
            """
            SELECT DATE(created_at) AS day, COUNT(*) AS cnt
            FROM tickets
            WHERE DATE(created_at) >= ?
            GROUP BY day ORDER BY day
            """,
            (cutoff,),
        ).fetchall()
        resolved_rows = conn.execute(
            """
            SELECT DATE(updated_at) AS day, COUNT(*) AS cnt
            FROM tickets
            WHERE status IN ('resolved','closed') AND DATE(updated_at) >= ?
            GROUP BY day ORDER BY day
            """,
            (cutoff,),
        ).fetchall()

    created_map = {r["day"]: r["cnt"] for r in created_rows}
    resolved_map = {r["day"]: r["cnt"] for r in resolved_rows}
    all_days = sorted(set(created_map) | set(resolved_map))

    return [
        TicketTrendPoint(
            date=day,
            created=created_map.get(day, 0),
            resolved=resolved_map.get(day, 0),
        )
        for day in all_days
    ]


def get_realtime_events(db_path: str, limit: int = 20) -> list[RealtimeEvent]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT event_id, event_type, channel, intent, customer_id, created_at
            FROM audit_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        RealtimeEvent(
            event_id=r["event_id"],
            event_type=r["event_type"],
            channel=r["channel"] or "",
            intent=r["intent"] or "",
            customer_id=r["customer_id"] or "",
            created_at=r["created_at"],
        )
        for r in rows
    ]
