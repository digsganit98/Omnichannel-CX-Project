"""Attrition-risk scorer (rule-based, not ML).

Produces a Low / Medium / High band plus the top reasons for an agent panel.
Named "attrition risk", not "churn": there are no historical churn/outcome labels
in this data, so this is a transparent heuristic over known warning signs — never
a validated prediction.

Rules (v2, agreed):
  - Override -> High: any customer message contains exit language.
  - Strong signs: card dpd >= 30; bad mood (>= 40% of recent turns 'high' urgency);
    stuck ticket (open ticket past sla_due_at, or > 3 days old if no SLA).
  - Weak signs: card dpd 1-29; below-min balance (avg_monthly_balance <
    min_balance_required, a proxy for a sustained shortfall — no balance history
    exists); fraud/chargeback flag; thin relationship (<= 1 product type);
    new customer (tenure < 6 months); >= 3 inbound contacts in last 30 days.
  - Banding: exit language -> High; >= 2 strong -> High; 1 strong OR >= 3 weak ->
    Medium; else Low.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Exit-intent phrases (lowercased substring match) — the strongest single signal.
EXIT_PHRASES = (
    "close my account",
    "closing my account",
    "close the account",
    "switch bank",
    "switching to",
    "leave the bank",
    "leaving the bank",
    "ombudsman",
    "cancel my",
)


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        # Accept both 'YYYY-MM-DD' and full ISO timestamps.
        if len(text) <= 10:
            return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def score_attrition(
    *,
    credit_cards: list[dict],
    accounts: list[dict],
    product_type_count: int,
    registration_date,
    tickets: list[dict],
    turns: list[dict],
    contacts_30d: int,
    now: datetime | None = None,
) -> dict:
    """Return {"band": "High|Medium|Low", "reasons": [str, ...],
    "strong": int, "weak": int, "override": bool}.

    `turns` and `tickets` are this customer's own turns/tickets. `reasons` are
    ordered strong-first, then weak; the caller shows the top 1-2.
    """
    now = now or datetime.now(timezone.utc)
    strong: list[str] = []
    weak: list[str] = []

    # ── Override: exit-intent language in any inbound (customer) message ──────
    override = False
    for turn in turns:
        if turn.get("direction") == "inbound":
            text = (turn.get("text") or "").lower()
            if any(phrase in text for phrase in EXIT_PHRASES):
                override = True
                break

    # ── Card delinquency (dpd) ───────────────────────────────────────────────
    max_dpd = 0
    fraud_flagged = False
    for card in credit_cards:
        dpd = card.get("dpd") or 0
        if dpd and dpd > max_dpd:
            max_dpd = dpd
        if card.get("fraud_flag") or card.get("chargeback_flag"):
            fraud_flagged = True
    if max_dpd >= 30:
        strong.append(f"{max_dpd}d overdue")
    elif max_dpd >= 1:
        weak.append(f"{max_dpd}d overdue")

    # ── Bad mood: >= 40% of recent turns are 'high' urgency ──────────────────
    urg = [(t.get("urgency") or "").lower() for t in turns if t.get("urgency")]
    if urg:
        high_share = sum(1 for u in urg if u == "high") / len(urg)
        if high_share >= 0.40:
            strong.append("mood worsening")

    # ── Stuck ticket: open ticket past SLA, or > 3 days old if no SLA ─────────
    stuck = False
    for ticket in tickets:
        if (ticket.get("status") or "").lower() != "open":
            continue
        sla = _parse_dt(ticket.get("sla_due_at"))
        created = _parse_dt(ticket.get("created_at"))
        if sla is not None:
            if now > sla:
                stuck = True
                break
        elif created is not None and (now - created).days > 3:
            stuck = True
            break
    if stuck:
        strong.append("stuck ticket")

    # ── Below-min balance (weak; proxy for sustained shortfall) ──────────────
    for acct in accounts:
        bal = acct.get("avg_monthly_balance")
        minbal = acct.get("min_balance_required")
        if bal is not None and minbal is not None and bal < minbal:
            weak.append("below-min balance")
            break

    # ── Fraud / chargeback on file (weak) ────────────────────────────────────
    if fraud_flagged:
        weak.append("fraud/chargeback on file")

    # ── Thin relationship (weak) ─────────────────────────────────────────────
    if product_type_count <= 1:
        weak.append("thin relationship")

    # ── New customer < 6 months (weak) ───────────────────────────────────────
    reg = _parse_dt(registration_date)
    if reg is not None and (now - reg).days < 182:
        weak.append("new customer")

    # ── Repeat contact: >= 3 inbound contacts in 30 days (weak) ──────────────
    if contacts_30d >= 3:
        weak.append(f"{contacts_30d} contacts/30d")

    # ── Banding ──────────────────────────────────────────────────────────────
    if override:
        band = "High"
        reasons = ["mentioned leaving"] + strong + weak
    elif len(strong) >= 2:
        band = "High"
        reasons = strong + weak
    elif len(strong) == 1 or len(weak) >= 3:
        band = "Medium"
        reasons = strong + weak
    else:
        band = "Low"
        reasons = strong + weak

    return {
        "band": band,
        "reasons": reasons,
        "strong": len(strong),
        "weak": len(weak),
        "override": override,
    }
