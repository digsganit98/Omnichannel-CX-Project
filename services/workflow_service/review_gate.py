"""Human-in-the-loop review gate.

Decides whether the AI's composed reply should be HELD as an editable draft for a
human agent to review/correct and send manually, instead of being auto-delivered to
the customer.

Rule (deliberately simple, see docs/Sayantini-session-changes-log.md "Fix 10"):
    HOLD the reply if and only if ``ticket_decision.hold_required`` is True.

``hold_required`` defaults to ``required``, so this is today's behaviour exactly. It is read
separately because "does a ticket exist?" and "does a human review this?" are different
questions that happened to share one value — see TicketDecision.

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


# Rule 2c hold reasons (services/agent_service/handoff.py). Kept as a module constant
# because they are consulted BEFORE the level early-returns as well as inside the
# general mapping below.
_HANDOFF_LABELS = {
    "handoff_human_requested": "Customer asked for a human",
    "handoff_service_failure_asserted": "Customer says we already failed them",
    "handoff_emergency": "Emergency — time-critical",
    "handoff_distress": "Customer in distress",
    "handoff_approval_needed": "Approval needed — customer asked for a decision",
}


def _friendly_reason(level: str, ticket_reason: str) -> str:
    """Human-readable hold reason for the admin UI, derived from level + ticket reason."""
    # A Rule 2c handoff code outranks the level label. The level says HOW HARD the query
    # is; the handoff code says WHY A PERSON IS NEEDED, which is what the agent opening
    # the queue actually has to act on. Checked before the level early-returns below,
    # which otherwise swallow it: a real service-failure complaint displayed as the
    # generic "Assisted resolution (L2)" and the agent could not see it had been flagged
    # as "we already failed this customer".
    if (ticket_reason or "").startswith("handoff_"):
        handoff_label = _HANDOFF_LABELS.get(ticket_reason)
        if handoff_label:
            return handoff_label

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
        # The customer wants an outcome (a reversal, a waiver, a claim honoured), not
        # information — a decision only a person can make. Distinct from "assisted
        # resolution", which means we could not retrieve what they asked for.
        "approval_required": "Approval needed — customer asked for a decision",
    }
    return mapping.get(code, "Escalated — needs human review")


def should_hold_for_review(ticket_decision, resolution=None) -> ReviewGateResult:
    """Return whether the reply should be held for human review.

    Args:
        ticket_decision: the TicketDecision (has ``required: bool`` and ``reason: str|None``).
            If falsy (e.g. rejected/unregistered path with no decision), we never hold.
        resolution: optional QueryResolution — read only for the friendly reason label.
    """
    # Reads hold_required, not required. They are the same value today (hold_required
    # defaults to required), so nothing changes yet - but the hold now has its own name, so a
    # later phase can create a ticket for every query without every one of them being held.
    if ticket_decision:
        hold_required = getattr(ticket_decision, "hold_required", None)
        if hold_required is None:  # older callers / plain stubs without the field
            hold_required = getattr(ticket_decision, "required", False)
    else:
        hold_required = False
    if not bool(hold_required):
        return ReviewGateResult(hold=False)

    ticket_reason = getattr(ticket_decision, "reason", "") or ""
    level = _level_of(resolution) if resolution is not None else ""
    return ReviewGateResult(
        hold=True,
        reason=_friendly_reason(level, ticket_reason),
        reason_code=ticket_reason or level or "ticket_required",
        details={"resolution_level": level, "ticket_reason": ticket_reason},
    )
