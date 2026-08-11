import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_key
from services.neo4j_service.client import Neo4jClient
from services.attrition_service.scorer import score_attrition
from services.neo4j_service.queries import (
    get_accounts,
    get_claim_status,
    get_credit_cards,
    get_customer_by_id,
    get_customer_by_identifier,
    get_fixed_deposits,
    get_loan_status,
    get_policy_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/customers",
    tags=["admin"],
    dependencies=[Depends(require_admin_key)],
)


@lru_cache
def _neo4j() -> Neo4jClient:
    return Neo4jClient()


def _parse_date(value) -> datetime | None:
    """Parse a 'YYYY-MM-DD' event date string; None if missing/malformed."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _upcoming_event(client, neo4j_cid: str) -> dict | None:
    """Most-urgent product event for a customer: overdue items first (most days
    overdue wins), otherwise the soonest upcoming. Scans card payment due dates
    (incl. dpd), FD maturities, and policy premium due dates. Returns
    {label, date, days, overdue} — days is negative when overdue — or None."""
    today = datetime.now(timezone.utc)
    candidates: list[dict] = []

    for card in get_credit_cards(client, neo4j_cid):
        due = _parse_date(card.get("payment_due_date"))
        dpd = card.get("dpd") or 0
        if dpd and dpd > 0:
            candidates.append({"label": "Card payment", "date": card.get("payment_due_date"),
                               "days": -int(dpd), "overdue": True})
        elif due:
            days = (due - today).days
            candidates.append({"label": "Card payment", "date": card.get("payment_due_date"),
                               "days": days, "overdue": days < 0})

    for fd in get_fixed_deposits(client, neo4j_cid):
        mat = _parse_date(fd.get("maturity_date"))
        if mat:
            days = (mat - today).days
            candidates.append({"label": "FD matures", "date": fd.get("maturity_date"),
                               "days": days, "overdue": days < 0})

    for pol in get_policy_status(client, neo4j_cid):
        due = _parse_date(pol.get("next_premium_due"))
        if due:
            days = (due - today).days
            candidates.append({"label": "Premium due", "date": pol.get("next_premium_due"),
                               "days": days, "overdue": days < 0})

    # Keep only agent-relevant events: overdue by <= 90 days, or upcoming within
    # 90 days. Drops stale items (e.g. an FD that matured years ago) and far-off
    # future events.
    candidates = [c for c in candidates if -90 <= c["days"] <= 90]
    if not candidates:
        return None
    # Overdue first (most overdue = smallest days), then soonest upcoming.
    overdue = [c for c in candidates if c["overdue"]]
    if overdue:
        return min(overdue, key=lambda c: c["days"])
    return min(candidates, key=lambda c: c["days"])


def _fmt_inr(value) -> str:
    """Compact rupee formatting for node captions ('₹10,65,000'); '' when absent."""
    try:
        return f"₹{int(float(str(value).replace(',', ''))):,}"
    except (ValueError, TypeError):
        return ""


def _resolve_graph_customer(customer_id: str):
    """Map a SQLite customer_id to its Neo4j customer via known channel identifiers.

    Same namespace problem the orchestration pipeline solves (Fix 63): SQLite keys on
    ``cust_…`` while the graph keys on ``CRN…``. Returns (client, neo4j_customer) or
    (client, None) for an unverified sender with no graph node.
    """
    repo = get_repository()
    client = _neo4j()
    for row in repo.list_customer_identifiers(customer_id) or []:
        found = (
            get_customer_by_id(client, row["identifier"])
            if row["channel"] == "graph"
            else get_customer_by_identifier(client, row["identifier"])
        )
        if found:
            return client, found
    return client, None


@router.get("/{customer_id}/graph-view")
def customer_graph_view(customer_id: str) -> dict:
    """Customer neighbourhood as ``{nodes, edges}`` for the admin knowledge-graph view.

    One hub Customer node plus its products, the claims hanging off each policy, and any
    tickets. ``health`` is a derived severity (ok / warn / crit / neutral) so the renderer
    can colour by "needs attention" rather than by node type.
    """
    empty = {"customer_id": customer_id, "resolved": False, "nodes": [], "edges": []}
    try:
        client, customer = _resolve_graph_customer(customer_id)
    except Exception as exc:
        logger.warning("graph_view_lookup_failed customer=%s: %s", customer_id, exc)
        return empty
    if not customer:
        return empty

    cid = customer["customer_id"]
    nodes: list[dict] = [{
        "id": cid,
        "type": "Customer",
        "label": customer.get("name") or cid,
        "sub": " · ".join(x for x in (customer.get("segment"), customer.get("city")) if x),
        "health": "hub",
        "props": {k: customer.get(k) for k in ("customer_id", "segment", "city", "email", "phone")},
    }]
    edges: list[dict] = []

    def add(node_id, ntype, label, sub, health, rel, source=cid, props=None):
        nodes.append({"id": node_id, "type": ntype, "label": label,
                      "sub": sub, "health": health, "props": props or {}})
        edges.append({"source": source, "target": node_id, "rel": rel})

    for a in get_accounts(client, cid):
        bal = a.get("avg_monthly_balance")
        minb = a.get("min_balance_required") or 0
        below = _num(bal) is not None and _num(minb) and _num(bal) < _num(minb)
        add(f"acct:{a.get('account_number')}", "Account",
            f"{a.get('account_type') or 'Account'} {a.get('account_sub_type') or ''}".strip(),
            f"{_fmt_inr(bal)} avg" + (" · below min" if below else ""),
            "warn" if below else ("ok" if str(a.get("status")).lower() == "active" else "neutral"),
            "HAS_ACCOUNT", props=a)

    for cc in get_credit_cards(client, cid):
        dpd = int(_num(cc.get("dpd")) or 0)
        health = "crit" if dpd >= 30 else ("warn" if dpd > 0 or cc.get("fraud_flag") else "ok")
        sub = f"Limit {_fmt_inr(cc.get('credit_limit'))} · due {_fmt_inr(cc.get('balance_due'))}"
        add(f"card:{cc.get('card_id')}", "CreditCard",
            f"{cc.get('card_network') or 'Card'} {cc.get('card_variant') or ''}".strip()
            + (f" · dpd {dpd}" if dpd else ""),
            sub, health, "HAS_CREDIT_CARD", props=cc)

    for fd in get_fixed_deposits(client, cid):
        add(f"fd:{fd.get('fd_id')}", "FixedDeposit", fd.get("fd_id") or "FD",
            f"{_fmt_inr(fd.get('principal_amount'))} · {fd.get('interest_rate')}%",
            "ok" if str(fd.get("status")).lower() == "active" else "neutral",
            "HAS_FD", props=fd)

    for l in get_loan_status(client, cid):
        add(f"loan:{l.get('loan_id')}", "Loan", l.get("loan_type") or "Loan",
            f"{_fmt_inr(l.get('amount_inr'))} · {l.get('status')}",
            "ok" if str(l.get("status")).lower() == "active" else "neutral",
            "HAS_LOAN", props=l)

    # Policies hold their claims — the two-hop shape a flat list cannot show.
    policies = get_policy_status(client, cid)
    claims = get_claim_status(client, cid)
    policy_ids = {p.get("policy_id") for p in policies}
    for p in policies:
        add(f"pol:{p.get('policy_id')}", "Policy", f"{p.get('policy_type') or 'Policy'} policy",
            f"Premium due {p.get('next_premium_due') or 'n/a'}",
            "warn" if p.get("next_premium_due") else "ok", "HAS_POLICY", props=p)

    for cl in claims:
        status = str(cl.get("status") or "").lower()
        health = "crit" if "reject" in status else ("ok" if "approv" in status else "warn")
        # Attach to the owning policy when known, else straight to the customer.
        parent = next((f"pol:{p.get('policy_id')}" for p in policies
                       if p.get("policy_type") and p.get("policy_type") == cl.get("policy_type")), cid)
        add(f"clm:{cl.get('claim_id')}", "Claim", f"{cl.get('claim_type') or 'Claim'}",
            f"{cl.get('status')} · {_fmt_inr(cl.get('amount_claimed'))}",
            health, "HAS_CLAIM", source=parent, props=cl)

    # Tickets (Fix 63 put these in the graph; read them from SQLite, the system of record).
    try:
        for t in get_repository().list_tickets():
            if t.get("customer_id") != customer_id:
                continue
            st = str(t.get("status") or "").lower()
            add(f"tkt:{t.get('ticket_id')}", "Ticket", t.get("ticket_id") or "Ticket",
                f"{t.get('intent') or ''} · {t.get('status')}",
                "neutral" if st in ("resolved", "closed") else "warn",
                "HAS_TICKET", props={k: t.get(k) for k in ("ticket_id", "intent", "status", "priority")})
    except Exception as exc:
        logger.warning("graph_view_tickets_failed customer=%s: %s", customer_id, exc)

    counts: dict[str, int] = {}
    for n in nodes:
        counts[n["type"]] = counts.get(n["type"], 0) + 1
    return {
        "customer_id": customer_id,
        "graph_customer_id": cid,
        "resolved": True,
        "nodes": nodes,
        "edges": edges,
        "counts": counts,
    }


def _num(value):
    """Best-effort numeric coercion; None when the value isn't a number."""
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


@router.get("/{customer_id}/graph")
def customer_graph(customer_id: str) -> dict:
    """Customer snapshot for the agent panel: identifiers, tenure (registration
    date), segment, contacts in the last 30 days, and the most-urgent upcoming
    product event. Keeps loan_count/claim_count for backward compatibility."""
    repo = get_repository()
    since_iso = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    contacts_30d = repo.count_recent_inbound(customer_id, since_iso)

    identifiers = repo.list_customer_identifiers(customer_id)
    base = {
        "name": None,
        "loan_count": 0, "claim_count": 0, "identifiers": identifiers or [],
        "registration_date": None, "segment": None,
        "contacts_30d": contacts_30d, "upcoming_event": None, "attrition": None,
    }
    if not identifiers:
        return base

    try:
        client = _neo4j()
        neo4j_cid = None
        registration_date = None
        segment = None
        graph_name = None
        for row in identifiers:
            customer = (
                get_customer_by_id(client, row["identifier"])
                if row["channel"] == "graph"
                else get_customer_by_identifier(client, row["identifier"])
            )
            if customer:
                neo4j_cid = customer["customer_id"]
                registration_date = customer.get("registration_date")
                segment = customer.get("segment")
                graph_name = customer.get("name")
                break

        if not neo4j_cid:
            return base

        loans = get_loan_status(client, neo4j_cid)
        claims = get_claim_status(client, neo4j_cid)
        cards = get_credit_cards(client, neo4j_cid)
        accounts = get_accounts(client, neo4j_cid)
        fds = get_fixed_deposits(client, neo4j_cid)
        policies = get_policy_status(client, neo4j_cid)
        product_type_count = sum(
            1 for products in (loans, cards, accounts, fds, policies) if products
        )

        # Attrition risk (rule-based) over BFSI + conversation signals.
        cust_tickets = [t for t in repo.list_tickets() if t.get("customer_id") == customer_id]
        cust_turns = repo.list_customer_turns(customer_id)
        attrition = score_attrition(
            credit_cards=cards,
            accounts=accounts,
            product_type_count=product_type_count,
            registration_date=registration_date,
            tickets=cust_tickets,
            turns=cust_turns,
            contacts_30d=contacts_30d,
        )

        return {
            **base,
            "name": graph_name,
            "loan_count": len(loans),
            "claim_count": len(claims),
            "registration_date": registration_date,
            "segment": segment,
            "upcoming_event": _upcoming_event(client, neo4j_cid),
            "attrition": attrition,
        }
    except Exception as exc:
        logger.warning("neo4j_graph_lookup_failed customer=%s: %s", customer_id, exc)
        return base
