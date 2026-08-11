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
