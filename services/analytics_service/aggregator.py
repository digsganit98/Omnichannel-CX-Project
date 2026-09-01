import sqlite3
from datetime import datetime, timedelta, timezone

from .metrics import (
    AgentMetrics,
    ChannelCount,
    ChannelMetrics,
    IntentCount,
    IntentMetrics,
    LabelCount,
    OverviewMetrics,
    RealtimeEvent,
    SentimentMetrics,
    SolutionPerformanceMetrics,
    TicketTrendPoint,
)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# Analytics counts WORK, so every "open" figure here means SERVICEABLE - a ticket a human
# is on. Under the ticket-model redesign every customer query gets a LOGGED ticket purely
# as a grouping id; counting those as open would inflate the headline queue by roughly 4x
# and make "open tickets" mean "messages received". These are written as inclusion lists
# because the previous form, `status <> 'closed'`, silently absorbs any new status.
_SERVICEABLE_SQL = "status IN ('open','in_progress')"
_CLOSED_SQL = "status = 'closed'"


def get_overview(db_path: str) -> OverviewMetrics:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN status IN ('open','in_progress') THEN 1 ELSE 0 END) AS open_cnt,
                SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) AS resolved_cnt,
                SUM(CASE WHEN escalation_reason IS NOT NULL AND escalation_reason != '' THEN 1 ELSE 0 END) AS escalated_cnt,
                -- An SLA can only be breached on work someone owes: a logging ticket has
                -- no promised response, so it cannot breach.
                SUM(CASE WHEN sla_due_at IS NOT NULL AND sla_due_at < datetime('now')
                              AND status IN ('open','in_progress') THEN 1 ELSE 0 END) AS sla_breach_cnt
            FROM tickets
            """
        ).fetchone()

        avg_row = conn.execute(
            """
            SELECT AVG(
                (julianday(updated_at) - julianday(created_at)) * 1440
            ) AS avg_mins
            FROM tickets
            WHERE status = 'closed'
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
        # Count each ticket ONCE, on the real channel it arrived on. The ticket's channel is the
        # channel of the turn(s) carrying its ticket_id (email / web_chat / whatsapp).
        # (The old query joined tickets → channel_identities, which (a) surfaced internal identifier
        #  types like 'graph'/'portal' that are NOT contact channels, and (b) counted a ticket once
        #  per identity the customer had, inflating every channel to a flat identical number.)
        ticket_rows = conn.execute(
            """
            SELECT channel, COUNT(*) AS cnt
            FROM (
                SELECT t.ticket_id, MIN(ct.channel) AS channel
                FROM tickets t
                JOIN conversation_turns ct ON ct.ticket_id = t.ticket_id
                WHERE ct.channel IS NOT NULL AND ct.channel != ''
                GROUP BY t.ticket_id
            )
            GROUP BY channel
            """
        ).fetchall()

        # Real customer-facing channels only (exclude internal identifier types).
        msg_rows = conn.execute(
            """
            SELECT channel, COUNT(*) AS cnt
            FROM conversation_turns
            WHERE channel IS NOT NULL AND channel != ''
            GROUP BY channel
            """
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


# Map a numeric priority_score (0-100) to a risk band for the "by risk band" chart.
def _risk_band(score: float) -> str:
    if score >= 80:
        return "Critical"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Medium"
    return "Low"


def get_solution_performance(db_path: str) -> SolutionPerformanceMetrics:
    """Operational 'state of the queue right now' metrics for the Solution Performance section.

    Formulas (agreed with the product owner):
      - escalation_rate = escalated tickets / total inbound customer queries.
        The denominator is INBOUND TURNS (every query the customer actually sent), NOT
        tickets/conversations — so routine non-escalating queries pull the rate down and it
        stays a real 0-100% rate instead of saturating toward 100%.
      - avg_risk_score = AVG(priority_score) over OPEN tickets (current queue heat).
      - critical_open  = count of OPEN tickets with priority='critical'.
      - drafts_handled = reply_drafts with status='sent' (human-in-the-loop throughput).
      - by_risk_band   = OPEN tickets bucketed by priority_score band.
      - by_escalation_reason = escalated tickets grouped by escalation_reason.
    """
    _open = _SERVICEABLE_SQL
    _escalated = "escalation_reason IS NOT NULL AND escalation_reason != ''"
    with _connect(db_path) as conn:
        escalations = conn.execute(
            f"SELECT COUNT(*) FROM tickets WHERE {_escalated}"
        ).fetchone()[0] or 0
        inbound = conn.execute(
            "SELECT COUNT(*) FROM conversation_turns WHERE direction = 'inbound'"
        ).fetchone()[0] or 0
        avg_risk = conn.execute(
            f"SELECT AVG(priority_score) FROM tickets WHERE {_open}"
        ).fetchone()[0] or 0.0
        critical_open = conn.execute(
            f"SELECT COUNT(*) FROM tickets WHERE priority = 'critical' AND {_open}"
        ).fetchone()[0] or 0
        drafts_handled = conn.execute(
            "SELECT COUNT(*) FROM reply_drafts WHERE status = 'sent'"
        ).fetchone()[0] or 0

        # Risk-band breakdown (open tickets, bucketed in Python so the bands live in one place).
        band_counts: dict[str, int] = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        for r in conn.execute(f"SELECT priority_score FROM tickets WHERE {_open}"):
            band_counts[_risk_band(r[0] or 0.0)] += 1

        reason_rows = conn.execute(
            f"SELECT escalation_reason AS reason FROM tickets WHERE {_escalated}"
        ).fetchall()

    # Aggregate AFTER prettifying so raw codes that map to the same label
    # (e.g. assisted_resolution_required:transaction_dispute and :loan_status) merge
    # into one bar instead of appearing twice.
    reason_counts: dict[str, int] = {}
    for r in reason_rows:
        label = _pretty_reason(r["reason"])
        reason_counts[label] = reason_counts.get(label, 0) + 1
    reason_sorted = sorted(reason_counts.items(), key=lambda kv: kv[1], reverse=True)

    rate = round((escalations / inbound) * 100, 1) if inbound else 0.0
    return SolutionPerformanceMetrics(
        escalation_rate_pct=rate,
        escalations=escalations,
        inbound_queries=inbound,
        avg_risk_score=round(avg_risk, 1),
        critical_open=critical_open,
        drafts_handled=drafts_handled,
        by_risk_band=[
            LabelCount(label=band, count=band_counts[band])
            for band in ("Critical", "High", "Medium", "Low")
            if band_counts[band] > 0
        ],
        by_escalation_reason=[
            LabelCount(label=label, count=cnt) for label, cnt in reason_sorted
        ],
    )


# Turn a raw escalation_reason code into a short human label for the chart.
def _pretty_reason(reason: str) -> str:
    if not reason:
        return "Other"
    base = reason.split(":", 1)[0]  # drop the ":intent" suffix (assisted_resolution_required:x)
    labels = {
        "assisted_resolution_required": "Assisted resolution",
        "low_retrieval_confidence": "Low confidence",
        "high_urgency": "High urgency",
        "critical_escalation": "Critical",
    }
    return labels.get(base, base.replace("_", " ").title())


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
            WHERE status = 'closed' AND DATE(updated_at) >= ?
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
