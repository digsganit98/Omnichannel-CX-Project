"""Human-in-the-loop review gate.

Decides whether the AI's composed reply should be HELD as an editable draft for a
human agent to review/correct and send manually, instead of being auto-delivered to
the customer.

Rule (deliberately simple, see docs/session-changes-log.md "Fix 10"):
    HOLD the reply if and only if ``ticket_decision.required`` is True.

``ticket_decision.required`` is already the single source of truth for escalation — it
folds in the L1/L2/L3 resolution level (L3 critical, L2 assisted) *and* every L1 case
that escalates via an intent rule (customer asked for a human, high urgency, weak
retrieval, repeat unresolved query, etc.). Gating on this one boolean means the hold
decision can never drift out of sync with the ticketing logic.

We additionally read the resolution level / ticket reason only to produce a friendlier
label for the admin UI ("Critical escalation (L3)", "Assisted resolution (L2)", ...).
The label never affects the hold decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReviewGateResult:
    hold: bool
    reason: str = ""          # short, human-readable label for the admin UI
    reason_code: str = ""     # stable machine code (ticket_decision.reason or level)
    details: dict = field(default_factory=dict)


def _level_of(resolution) -> str:
    """Best-effort L1/L2/L3 from the resolution decision; '' if unavailable."""
    decision = getattr(resolution, "resolution_decision", None) or {}
    return str(decision.get("resolution_level", "")).upper()


def _friendly_reason(level: str, ticket_reason: str) -> str:
    """Human-readable hold reason for the admin UI, derived from level + ticket reason."""
    if level == "L3":
        return "Critical escalation (L3)"
    if level == "L2":
        return "Assisted resolution (L2)"

    # L1-via-intent-rule escalations: map the known ticket_decision.reason prefixes to a
    # friendly phrase; fall back to a generic label for anything unmapped.
    code = (ticket_reason or "").split(":", 1)[0]
    mapping = {
        "customer_requested_human": "Escalated: customer requested a human",
        "manual_review_required": "Escalated: manual review required",
        "no_live_banking_data": "Escalated: needs live banking data",
        "high_urgency": "Escalated: high urgency",
        "low_intent_confidence": "Escalated: low intent confidence",
        "repeated_unresolved_query": "Escalated: repeated unresolved query",
        "repeat_customer_new_issue": "Escalated: repeat customer, new issue",
        "knowledge_not_found": "Escalated: no knowledge found",
        "low_retrieval_confidence": "Escalated: weak knowledge match",
        "secondary_intent_manual_review": "Escalated: secondary issue needs review",
        "critical_escalation": "Critical escalation",
        "assisted_resolution_required": "Assisted resolution",
    }
    return mapping.get(code, "Escalated — needs human review")


def should_hold_for_review(ticket_decision, resolution=None) -> ReviewGateResult:
    """Return whether the reply should be held for human review.

    Args:
        ticket_decision: the TicketDecision (has ``required: bool`` and ``reason: str|None``).
            If falsy (e.g. rejected/unregistered path with no decision), we never hold.
        resolution: optional QueryResolution — read only for the friendly reason label.
    """
    required = bool(getattr(ticket_decision, "required", False)) if ticket_decision else False
    if not required:
        return ReviewGateResult(hold=False)

    ticket_reason = getattr(ticket_decision, "reason", "") or ""
    level = _level_of(resolution) if resolution is not None else ""
    return ReviewGateResult(
        hold=True,
        reason=_friendly_reason(level, ticket_reason),
        reason_code=ticket_reason or level or "ticket_required",
        details={"resolution_level": level, "ticket_reason": ticket_reason},
    )
