import hashlib
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_key
from services.neo4j_service.client import Neo4jClient
from services.neo4j_service.queries import (
    get_accounts,
    get_case_messages,
    get_charges,
    get_claim_status,
    get_credit_cards,
    get_customer_by_id,
    get_customer_by_identifier,
    get_fixed_deposits,
    get_loan_status,
    get_policy_status,
    get_transactions,
)
from services.rag_service.groq_generator import GroqGenerator

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

    # Transactions are the one product a customer has DOZENS of (72 across the 5 demo
    # customers), so they cannot all join a radial layout sized for ~12 nodes. Only the
    # ones a dispute is actually about are shown: any transaction not in a settled state,
    # plus the most recent few. A fully-settled history contributes no nodes at all.
    transactions = get_transactions(client, cid, limit=8)
    unsettled = [t for t in transactions
                 if str(t.get("status") or "").lower() not in ("success", "settled", "completed")]
    for t in (unsettled or transactions[:3]):
        status = str(t.get("status") or "")
        settled = status.lower() in ("success", "settled", "completed")
        add(f"txn:{t.get('txn_id')}", "Transaction",
            f"{t.get('txn_type') or 'Txn'} {_fmt_inr(t.get('amount'))}",
            f"{t.get('channel') or ''} · {status}".strip(" ·"),
            "ok" if settled else "warn",
            "HAS_TRANSACTION", props=t)

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
    # OPEN ONLY — a resolved ticket is closed business, and including them let one node type
    # grow without bound: a long-standing customer accumulates tickets forever while the
    # radial layout is sized for ~12 nodes, so their products would eventually be crowded
    # out by their history. Matches the right panel's "Open Tickets (N)" card (Fix 47).
    # Resolved-ticket history stays visible in Lineage and the portal's My Tickets.
    ticket_ids: list[str] = []
    try:
        for t in get_repository().list_tickets():
            if t.get("customer_id") != customer_id:
                continue
            st = str(t.get("status") or "").lower()
            if st == "closed":
                continue
            scope = ((t.get("metadata") or {}).get("ticket_scope") or "")
            # "transaction_dispute:imps" → "imps": the specific matter, so two disputes
            # are distinguishable instead of rendering as identical nodes.
            detail = scope.split(":", 1)[1] if ":" in scope else ""
            add(f"tkt:{t.get('ticket_id')}", "Ticket", t.get("ticket_id") or "Ticket",
                f"{t.get('intent') or ''}{' · ' + detail if detail else ''} · {t.get('status')}",
                "warn",  # every ticket reaching here is open — resolved ones are skipped above
                "HAS_TICKET", props={k: t.get(k) for k in ("ticket_id", "intent", "status", "priority")})
            ticket_ids.append(t.get("ticket_id"))
    except Exception as exc:
        logger.warning("graph_view_tickets_failed customer=%s: %s", customer_id, exc)

    # Case messages are deliberately NOT added here. This panel is the customer's
    # 360 — what they hold and which cases are open — and per-message nodes crowd it
    # without adding to that. They belong in the per-reply provenance view, where the
    # question is "does THIS reply continue an existing case?" (see
    # conversations.py::turn_provenance, which returns the reply's own ticket + messages).

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
        "contacts_30d": contacts_30d, "upcoming_event": None,
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

        return {
            **base,
            "name": graph_name,
            "loan_count": len(loans),
            "claim_count": len(claims),
            "registration_date": registration_date,
            "segment": segment,
            "upcoming_event": _upcoming_event(client, neo4j_cid),
        }
    except Exception as exc:
        logger.warning("neo4j_graph_lookup_failed customer=%s: %s", customer_id, exc)
        return base


# ── Customer Context: the record, grouped into tabs by one LLM call ──────────
# Fixed category set. Every key is ALWAYS present in the response, even when empty:
# a missing key crashes the renderer on whichever field the model happened to omit,
# so the shape is enforced here rather than trusted from the model.
CONTEXT_CATEGORIES = ("risk", "holdings", "activity", "claims", "profile")

# The graph query defaults to 20. Ten covers any dispute conversation an agent is
# likely to be handling and roughly halves this part of the prompt.
CONTEXT_TXN_LIMIT = 10


def _ctx_lines(title: str, rows: list[dict], fields: tuple[str, ...]) -> list[str]:
    """Compact labelled lines for one group of records.

    Values are passed through verbatim - the prompt forbids the model from reformatting
    them, and any currency/date presentation happens in the browser where it is
    deterministic. Empty and zero values are dropped here as well as in the prompt:
    an agent reads a blank row as missing data rather than as nothing owed.
    """
    lines: list[str] = []
    for row in rows:
        parts = []
        for field in fields:
            value = row.get(field)
            if value in (None, "", "N/A", "None", 0, "0"):
                continue
            parts.append(f"{field}={value}")
        if parts:
            lines.append(f"  - {title}: " + ", ".join(parts))
    return lines


def _build_record_text(client, customer: dict) -> str:
    """The customer's record as compact text for the categoriser."""
    cid = customer["customer_id"]
    lines = [f"Customer: customer_id={cid}"]
    for field in ("name", "segment", "city", "email", "phone", "registration_date"):
        if customer.get(field):
            lines.append(f"  - {field}={customer[field]}")

    lines += _ctx_lines("Account", get_accounts(client, cid), (
        "account_type", "account_sub_type", "account_number", "status",
        "avg_monthly_balance", "min_balance_required", "branch"))
    lines += _ctx_lines("CreditCard", get_credit_cards(client, cid), (
        "card_network", "card_variant", "card_id", "credit_limit", "balance_due",
        "min_amount_due", "total_amount_due", "payment_due_date", "dpd",
        "penalty_details", "reward_points_balance", "fraud_flag", "chargeback_flag"))
    lines += _ctx_lines("FixedDeposit", get_fixed_deposits(client, cid), (
        "fd_id", "principal_amount", "interest_rate", "tenure_months",
        "maturity_date", "maturity_amount", "status"))
    lines += _ctx_lines("Loan", get_loan_status(client, cid), (
        "loan_id", "loan_type", "principal_amount", "outstanding_amount",
        "emi_amount", "next_due_date", "dpd", "status"))
    lines += _ctx_lines("Policy", get_policy_status(client, cid), (
        "policy_id", "policy_type", "status", "premium_inr", "coverage_inr",
        "next_premium_due"))
    lines += _ctx_lines("Transaction", get_transactions(client, cid, limit=CONTEXT_TXN_LIMIT), (
        "txn_id", "txn_date", "txn_type", "channel", "amount", "beneficiary_name",
        "status", "failure_reason"))
    lines += _ctx_lines("Claim", get_claim_status(client, cid), (
        "claim_id", "claim_type", "policy_type", "status", "amount_claimed",
        "amount_approved", "reason", "last_updated"))
    lines += _ctx_lines("Charge", get_charges(client, cid), (
        "charge_type", "amount", "charge_date", "reason", "reversal_status"))
    return "\n".join(lines)


def _normalise_categories(parsed: dict) -> dict:
    """Force the model's output into the shape the renderer requires.

    Every category key present, always a list, every item a {label, value} pair with an
    optional {sub}. A model that returns a bare string, a nested object or a missing key
    degrades to a dropped item - never to a broken panel.
    """
    out: dict[str, list[dict]] = {}
    for key in CONTEXT_CATEGORIES:
        items = parsed.get(key)
        clean: list[dict] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or "").strip()
                value = item.get("value")
                value = "" if value is None else str(value).strip()
                if not label or not value:
                    continue
                entry = {"label": label, "value": value}
                sub = str(item.get("sub") or "").strip()
                # Drop a sub that adds nothing: a bare source field name (no spaces, the
                # snake_case the record was built from) or a restatement of the label or
                # value. The prompt forbids these; this is the guard for when it is
                # ignored, since each one costs a whole row in a narrow panel.
                if sub and sub.lower() not in (label.lower(), value.lower()):
                    if " " in sub or "-" in sub or not sub.replace("_", "").isalpha():
                        entry["sub"] = sub
                clean.append(entry)
        out[key] = clean
    return out


@router.get("/{customer_id}/context")
def customer_context(customer_id: str, refresh: bool = False) -> dict:
    """The customer's record grouped into the right-panel Customer Context tabs.

    ONE LLM call per record, not per tab: the frontend renders every panel from this
    single response and switching tabs is a class toggle, never a request.

    Cached on a fingerprint of the record rather than on a turn id (see 013 vs 014):
    a case summary goes stale when a message arrives, a customer context goes stale
    when a FIELD changes. Same record -> cached row and zero tokens; any field
    different -> the hash differs and it regenerates.
    """
    empty = {"customer_id": customer_id, "status": "empty",
             "categories": {k: [] for k in CONTEXT_CATEGORIES}, "raw": None}
    try:
        client, customer = _resolve_graph_customer(customer_id)
    except Exception as exc:
        logger.warning("customer_context_lookup_failed customer=%s: %s", customer_id, exc)
        return empty
    if not customer:
        return empty

    try:
        record_text = _build_record_text(client, customer)
    except Exception:
        logger.exception("customer_context_record_build_failed customer=%s", customer_id)
        return empty
    if not record_text.strip():
        return empty

    record_hash = hashlib.sha256(record_text.encode("utf-8")).hexdigest()
    repo = get_repository()

    if not refresh:
        cached = repo.get_customer_context(customer_id)
        if cached and cached.get("record_hash") == record_hash:
            return {
                "customer_id": customer_id,
                "status": "cached",
                "generated_at": cached.get("created_at"),
                "categories": _normalise_categories(cached.get("categories") or {}),
                "raw": None,
            }

    result = GroqGenerator().categorize_customer_record(record_text)
    if result is None:
        # No LLM (quota, outage, no key). Say so rather than showing the agent an
        # empty panel that reads as "this customer has no records".
        return {"customer_id": customer_id, "status": "unavailable",
                "categories": {k: [] for k in CONTEXT_CATEGORIES}, "raw": None}

    if "raw" in result:
        # Parsing failed. Show what the model said rather than losing the content to a
        # failed guess; not cached, since a bad parse should be retried, not pinned.
        return {"customer_id": customer_id, "status": "raw",
                "categories": {k: [] for k in CONTEXT_CATEGORIES},
                "raw": result.get("raw")}

    categories = _normalise_categories(result.get("categories") or {})
    try:
        repo.save_customer_context(customer_id, record_hash, categories, result.get("model"))
    except Exception:
        logger.exception("customer_context_save_failed")  # serve it anyway; caching is best-effort

    return {"customer_id": customer_id, "status": "generated",
            "model": result.get("model"), "categories": categories, "raw": None}
