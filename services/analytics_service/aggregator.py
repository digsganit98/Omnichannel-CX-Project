import sqlite3
from datetime import datetime, timedelta, timezone

from shared.constants.priority_weights import PRIORITY_THRESHOLDS

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
                -- first_response_at (019) closes the other half: this is a RESPONSE SLA,
                -- so once a human has replied the promise is kept and the row can never
                -- breach afterwards. Without this test an answered ticket kept counting as
                -- breached for as long as it stayed open, which is the case a supervisor
                -- would have already dealt with. Must stay identical to sdSla() in app.js -
                -- the two disagreeing (2 vs 7) is exactly what this phase fixed.
                SUM(CASE WHEN sla_due_at IS NOT NULL AND sla_due_at < datetime('now')
                              AND status IN ('open','in_progress')
                              AND first_response_at IS NULL THEN 1 ELSE 0 END) AS sla_breach_cnt
            FROM tickets
            """
        ).fetchone()

        # Average handling time over cases a human actually worked.
        #
        # `status = 'closed'` is the right filter and was never wrong - what changed is WHICH
        # tickets reach closed. Under the ticket-model redesign every customer query gets a
        # LOGGED ticket, and closing is a live pipeline path (the customer says "that's
        # sorted" -> TicketAction.CLOSE), so a logging id created and closed within the same
        # exchange would drop a ~0-minute sample into the same average as a multi-day dispute
        # and drag this headline tile toward zero - while looking like an improvement.
        #
        # `escalation_reason IS NOT NULL` is the test for "a person was ever needed on this":
        # it is written when the ticket opens OPEN, and promotion (logged -> open) writes it
        # too, so a thread that started as a grouping id and later needed a human is still
        # counted. A ticket that never left LOGGED has none, and is excluded.
        avg_row = conn.execute(
            """
            SELECT AVG(
                (julianday(updated_at) - julianday(created_at)) * 1440
            ) AS avg_mins
            FROM tickets
            WHERE status = 'closed'
              AND escalation_reason IS NOT NULL AND escalation_reason != ''
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
        #
        # SERVICEABLE only. This query had NO status filter, which was correct while a ticket
        # meant "a human is needed" - under the ticket-model redesign every customer query gets
        # a LOGGED grouping id, so counting those would make ticket_count a second copy of
        # message_count and the chart would stop comparing the two things it exists to compare.
        ticket_rows = conn.execute(
            """
            SELECT channel, COUNT(*) AS cnt
            FROM (
                SELECT t.ticket_id, MIN(ct.channel) AS channel
                FROM tickets t
                JOIN conversation_turns ct ON ct.ticket_id = t.ticket_id
                WHERE ct.channel IS NOT NULL AND ct.channel != ''
                  AND t.status IN ('open','in_progress')
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
#
# Reads PRIORITY_THRESHOLDS rather than carrying its own numbers. These used to be a
# separate 80/50/25 scale, so a ticket stored priority='critical' (>= 70) charted as
# "High" - one score, two disagreeing labels on two screens. Nothing lands in the gap on
# today's data, which is exactly why it went unnoticed; sourcing both from one table is
# what stops it coming back.
def _risk_band(score: float) -> str:
    if score >= PRIORITY_THRESHOLDS["critical"]:
        return "Critical"
    if score >= PRIORITY_THRESHOLDS["high"]:
        return "High"
    if score >= PRIORITY_THRESHOLDS["medium"]:
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
    """What customers are contacting us ABOUT, counted from conversation_turns.

    Reads TURNS, not tickets - so it is unaffected by the ticket-model redesign, and no
    status filter belongs here. It has always counted every classified customer message,
    which is the right population for a demand chart. The title says "query intents" rather
    than "ticket intents" so it is not read as a view of the agent queue, where every other
    ticket figure on the dashboard means SERVICEABLE.
    """
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
    """Per-team workload. Every figure here counts WORK, so LOGGED is excluded.

    This query had no status filter at all: it counted every ticket as "handled" and
    averaged `updated_at - created_at` over all of them. Both were already imperfect
    (the average is meaningless on a ticket that is still open — that difference is just
    "time since the last administrative edit"), but they become WRONG under the
    ticket-model redesign, where every customer query gets a LOGGED ticket. "Handled"
    would quietly come to mean "messages received", inflated roughly 4x, on a dashboard.

    So each column now says which population it means:
      * handled     - SERVICEABLE: a human is on it, or was
      * avg_mins    - CLOSED only: elapsed time is only meaningful once the case ended
      * escalations - SERVICEABLE: a logging ticket has no escalation_reason anyway,
                      but stating it keeps the three columns consistent
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                assigned_team AS agent,
                SUM(CASE WHEN {_SERVICEABLE_SQL} THEN 1 ELSE 0 END) AS handled,
                AVG(CASE WHEN {_CLOSED_SQL}
                         THEN (julianday(updated_at) - julianday(created_at)) * 1440
                    END) AS avg_mins,
                SUM(CASE WHEN {_SERVICEABLE_SQL}
                          AND escalation_reason IS NOT NULL AND escalation_reason != ''
                         THEN 1 ELSE 0 END) AS escalations
            FROM tickets
            GROUP BY assigned_team
            HAVING handled > 0
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


# ── Today, for the agent console ──────────────────────────────────────────────────────
# Who replied is a per-turn fact: every reply a person sends is persisted with one of these
# sources (reply_drafts.py, conversations.py), and every other outbound turn is the AI's -
# except the automatic holding line, which is an acknowledgement, not an answer.
HUMAN_REPLY_SOURCES = {"manual_agent_reply", "agent_composed_reply", "opportunity_offer"}
_HOLDING_TEXT = "will help you with this shortly"


def _turn_meta(row) -> dict:
    import json
    try:
        return json.loads(row["metadata_json"] or "{}")
    except (TypeError, ValueError):
        return {}


def _parse_ts(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _median(values):
    values = sorted(values)
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def get_today_metrics(db_path: str, since: datetime) -> dict:
    """Three console KPIs from `since` (the browser's local midnight) until now.

    volume     replies sent by the AI vs by people, per channel and per hour since `since`
    agents     per person: replies by channel, drafts decided, first-reply SLA, and how the
               customer's next message felt
    attention  open cases where a person replied and the customer's NEXT message was
               negative, with nobody replying since. Not limited to today: an upset customer
               from yesterday still needs someone now.
    """
    since = since.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    with _connect(db_path) as conn:
        turns = conn.execute(
            "SELECT turn_id, conversation_id, ticket_id, channel, direction, text, metadata_json, created_at "
            "FROM conversation_turns ORDER BY created_at ASC"
        ).fetchall()
        tickets = {r["ticket_id"]: dict(r) for r in conn.execute("SELECT * FROM tickets").fetchall()}
        drafts = conn.execute(
            "SELECT status, draft_text, sent_text, decided_by, decided_at, channel FROM reply_drafts "
            "WHERE status IN ('sent','discarded') AND decided_at >= ?",
            (since.isoformat(),),
        ).fetchall()

    def kind(turn, meta):
        if turn["direction"] != "outbound":
            return "inbound"
        if meta.get("source") in HUMAN_REPLY_SOURCES:
            return "human"
        if _HOLDING_TEXT in (turn["text"] or "").lower():
            return "holding"
        return "ai"

    enriched = []
    for t in turns:
        meta = _turn_meta(t)
        enriched.append({"row": t, "meta": meta, "kind": kind(t, meta), "at": _parse_ts(t["created_at"])})

    # volume
    hours = max(1, int((now - since).total_seconds() // 3600) + 1)
    hourly = [{"ai": 0, "human": 0} for _ in range(min(hours, 48))]
    by_channel: dict = {}
    volume = {"ai": 0, "human": 0, "inbound": 0}
    for e in enriched:
        if not e["at"] or e["at"] < since:
            continue
        if e["kind"] == "inbound":
            volume["inbound"] += 1
            continue
        if e["kind"] not in ("ai", "human"):
            continue
        volume[e["kind"]] += 1
        ch = by_channel.setdefault(e["row"]["channel"] or "unknown", {"ai": 0, "human": 0})
        ch[e["kind"]] += 1
        slot = int((e["at"] - since).total_seconds() // 3600)
        if 0 <= slot < len(hourly):
            hourly[slot][e["kind"]] += 1

    # the next customer message after each turn, per conversation
    by_conv: dict = {}
    for e in enriched:
        by_conv.setdefault(e["row"]["conversation_id"], []).append(e)

    def next_inbound(conv_turns, idx):
        for later in conv_turns[idx + 1:]:
            if later["kind"] == "inbound":
                return later
        return None

    agents: dict = {}

    def agent(name):
        return agents.setdefault(name, {
            "actor": name, "replies": 0, "by_channel": {}, "drafts_sent_as_is": 0, "drafts_edited": 0,
            "drafts_replaced": 0, "sla_met": 0, "sla_total": 0, "first_reply_minutes": [],
            "mood_after": {"positive": 0, "neutral": 0, "negative": 0, "no_reply_yet": 0},
        })

    for conv_turns in by_conv.values():
        for idx, e in enumerate(conv_turns):
            if e["kind"] != "human" or not e["at"] or e["at"] < since:
                continue
            a = agent(str(e["meta"].get("actor") or "admin"))
            a["replies"] += 1
            ch = e["row"]["channel"] or "unknown"
            a["by_channel"][ch] = a["by_channel"].get(ch, 0) + 1
            reaction = next_inbound(conv_turns, idx)
            mood = (reaction["meta"].get("sentiment") or "neutral") if reaction else "no_reply_yet"
            a["mood_after"][mood if mood in a["mood_after"] else "neutral"] += 1

    for d in drafts:
        a = agent(str(d["decided_by"] or "admin"))
        if d["status"] == "discarded":
            a["drafts_replaced"] += 1
        elif (d["sent_text"] or "").strip() == (d["draft_text"] or "").strip():
            a["drafts_sent_as_is"] += 1
        else:
            a["drafts_edited"] += 1

    # First-reply SLA: a ticket whose first response landed today belongs to whoever sent
    # the first human reply on it.
    first_human: dict = {}
    for e in enriched:
        tid = e["row"]["ticket_id"]
        if e["kind"] == "human" and tid and tid not in first_human:
            first_human[tid] = e
    for tid, e in first_human.items():
        t = tickets.get(tid)
        responded = _parse_ts(t.get("first_response_at")) if t else None
        if not t or not responded or responded < since:
            continue
        a = agent(str(e["meta"].get("actor") or "admin"))
        created, due = _parse_ts(t.get("created_at")), _parse_ts(t.get("sla_due_at"))
        if created:
            a["first_reply_minutes"].append(max(0.0, (responded - created).total_seconds() / 60))
        if due:
            a["sla_total"] += 1
            a["sla_met"] += 1 if responded <= due else 0

    agent_rows = []
    for a in agents.values():
        mins = a.pop("first_reply_minutes")
        a["median_first_reply_minutes"] = round(_median(mins), 1) if mins else None
        agent_rows.append(a)
    agent_rows.sort(key=lambda a: (-a["replies"], a["actor"]))

    # attention: open, a person replied, the customer's next message was negative, and
    # nobody has replied since.
    attention = []
    for conv_id, conv_turns in by_conv.items():
        last_human_idx = None
        for idx, e in enumerate(conv_turns):
            if e["kind"] == "human":
                last_human_idx = idx
        if last_human_idx is None:
            continue
        reaction = next_inbound(conv_turns, last_human_idx)
        if not reaction or (reaction["meta"].get("sentiment") or "") != "negative":
            continue
        human = conv_turns[last_human_idx]
        ticket = tickets.get(reaction["row"]["ticket_id"]) or tickets.get(human["row"]["ticket_id"])
        if not ticket or ticket.get("status") not in ("open", "in_progress"):
            open_on_conv = [t for t in tickets.values()
                            if t["conversation_id"] == conv_id and t.get("status") in ("open", "in_progress")]
            if not open_on_conv:
                continue
            ticket = open_on_conv[0]
        attention.append({
            "conversation_id": conv_id,
            "ticket_id": ticket["ticket_id"],
            "replied_by": str(human["meta"].get("actor") or "admin"),
            "replied_at": human["row"]["created_at"],
            "customer_said": (reaction["row"]["text"] or "")[:280],
            "customer_said_at": reaction["row"]["created_at"],
            "sla_due_at": ticket.get("follow_up_due_at") or ticket.get("sla_due_at"),
        })
    attention.sort(key=lambda x: x["sla_due_at"] or "9999")

    return {
        "since": since.isoformat(),
        "volume": {**volume, "by_channel": by_channel, "hourly": hourly},
        "agents": agent_rows,
        "attention": attention,
    }
