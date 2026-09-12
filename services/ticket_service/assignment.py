"""Who a ticket belongs to.

Two hops, and the split matters: `assign_team` maps the classified intent to a QUEUE
(fraud_and_disputes, claims, ...), and `pick_agent` chooses a PERSON inside that queue.
The first has always existed; the second is what migration 019 made possible.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.constants.intents import INTENT_TO_TEAM

# How recently someone must have acted to count as available. Anyone quieter than this is
# skipped by auto-assign - not because they are "away" in any status they set, but because
# nothing they have done says they are at their desk. Manual assignment ignores this
# entirely: a human routing work may know something the timestamps do not.
AVAILABILITY_WINDOW_MINUTES = 60


def assign_team(intent: str) -> str:
    return INTENT_TO_TEAM.get(intent, "customer_support")


def availability(last_action_at: str | None, now: datetime | None = None) -> str:
    """Derived from what the person last DID, never from a status they set.

    An agent who forgets to mark themselves away still reads as away, because the input is
    their own activity (a ticket event they were the actor on, or a reply draft they
    decided). Nothing here is self-reported, so nothing here can be stale in the way a
    forgotten toggle is.

    NEVER ACTED is "unknown", not "away". Measured: on a freshly seeded database every
    agent has last_action_at = NULL, so treating that as away made auto_assign refuse
    every single ticket - correct by the letter of the rule and useless in practice, since
    a new deployment could never route anything until somebody had manually worked a case
    first. "Away" has to mean OBSERVED absence (they acted, but not for an hour), which a
    NULL cannot evidence either way.
    """
    if not last_action_at:
        return "unknown"
    now = now or datetime.now(timezone.utc)
    try:
        last = datetime.fromisoformat(last_action_at)
    except (TypeError, ValueError):
        return "away"
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    minutes = (now - last).total_seconds() / 60
    if minutes <= 15:
        return "active"
    if minutes <= AVAILABILITY_WINDOW_MINUTES:
        return "idle"
    return "away"


def pick_agent(agents: list[dict], team: str, now: datetime | None = None) -> str | None:
    """Least-loaded available agent on `team`, or None if the queue cannot take it.

    NOT round-robin. Round-robin assumes interchangeable agents; ours are team-bound by
    intent, so rotating across the whole roster would hand a fraud case to a loans officer.
    Balancing load WITHIN the team is the shape that fits.

    Two exclusions, both deliberate:

      * Operators (team IS NULL) are never auto-assigned to. A signed-in person can take
        any ticket in any team by hand - that is the point of being team-less - but the
        machine must not hand them work they never asked for.
      * Anyone at or over capacity is skipped, so auto-assign cannot pile a queue onto
        someone who is already full. If EVERY agent on the team is full or away the answer
        is None: the ticket stays unassigned and shows up in triage, which is honest. A
        fallback that assigned it anyway would hide the fact that the team is out of room.

    Ordering is (open_count, breaching, username): fewest tickets first, then whoever is
    carrying fewer breaches, then alphabetical so the choice is deterministic and a test
    can assert it.
    """
    # A ticket with no team has no queue to pick from. Without this guard `team=None`
    # matches every operator (whose team IS NULL by design) and auto-assign hands them
    # work - the exact thing the docstring above forbids. Caught by test, not by reading.
    if not team:
        return None
    now = now or datetime.now(timezone.utc)
    candidates = [
        a for a in agents
        if a.get("team") == team
        and (a.get("capacity") or 0) > (a.get("open_count") or 0)
        and availability(a.get("last_action_at"), now) != "away"
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda a: (a.get("open_count") or 0, a.get("breaching") or 0, a["username"]))
    return candidates[0]["username"]
