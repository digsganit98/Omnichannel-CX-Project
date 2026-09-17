"""Admin routes for agent-assist recommendations (next-best-action, cross-sell, ...).

Recommendations are surfaced to a human agent for approval/dismissal — never sent to
a customer automatically. See services/agent_assist_service/next_best_action.py.
"""

import hashlib
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_auth
# NextBestActionEngine's four `if` rules no longer drive the card - case_advisor does -
# but the class stays imported and on disk: tests/test_agent_assist.py exercises each rule
# directly, and deleting it would break a passing suite for no gain.
from services.agent_assist_service.next_best_action import NextBestActionEngine
# The SAME salutation the AI replies use: the customer's real name, or "Customer" when all
# we have is an email address. Reused rather than reimplemented so a drafted nudge and a
# pipeline reply cannot greet the same person two different ways.
from services.agent_service.orchestration_agents import _salutation
from services.agent_assist_service import case_advisor, case_reviewer, opportunity_engine
from services.rag_service.groq_generator import GroqGenerator
from shared.schemas.agent_assist import (
    ActionType,
    DRAFTABLE_ACTION_TYPES,
    NBADecisionUpdate,
    PIPELINE_ACTION_TYPES,
)
from shared.schemas.tickets import SERVICEABLE_TICKET_STATUSES

logger = logging.getLogger(__name__)

# Cross-sell/up-sell rows are "offers": Approve creates an editable reply draft
# (delivered over push channels), unlike operational NBA rows where Approve only
# records the decision.
_OFFER_ACTION_TYPES = {"cross_sell", "up_sell"}
# Marker channel on offer drafts — send_draft delivers these to ALL push
# channels (whatsapp + email) the customer has on record.
OFFER_DRAFT_CHANNEL = "offer"

router = APIRouter(prefix="/admin/agent-assist", tags=["admin"], dependencies=[Depends(require_admin_auth)])


def _advice_generator():
    """The model behind the Suggested Actions card. A seam, so tests can replace it."""
    return GroqGenerator()


def _try_neo4j():
    """Best-effort Neo4j client — recommendations degrade gracefully without one."""
    try:
        if os.getenv("NEO4J_ENABLED", "true").lower() != "true":
            return None
        from services.neo4j_service.client import Neo4jClient
        return Neo4jClient()
    except Exception:
        return None


def _review_generator():
    """The model behind the merged case review. A seam, so tests can replace it."""
    return GroqGenerator()


# One lock per case, so the three cards that share a review cannot each start their own.
#
# The cache below is written only AFTER a call returns. Opening a case fires all three
# right-panel requests at once, so all three read the cache before any of them has
# written it, all three miss, and all three call the LLM. Measured 2026-09-16 on
# tkt_b85a9efbd9fe: three case_review calls 19s/21s/23s, identical 5,113-char prompts,
# and because Groq's limit is per MINUTE (8,000 TPM) the two that lost the race came
# back 429 - one success, two failures, for a card set that needs exactly one call.
#
# A plain threading.Lock is the right size here: uvicorn runs a single worker (see
# docker-compose.yml) and these routes are sync `def`, so FastAPI runs them in its
# threadpool - the contention is between threads in one process, which is also why
# repository.py:144 uses an RLock. A multi-worker deployment would need this in the
# database instead; there is no such deployment.
#
# Keyed by ticket_id, never by conversation: one conversation holds several cases and
# two of them are independent reviews that SHOULD run separately.
_review_locks: dict[str, threading.Lock] = {}
_review_locks_guard = threading.Lock()


def _review_lock(ticket_id: str) -> threading.Lock:
    with _review_locks_guard:
        lock = _review_locks.get(ticket_id)
        if lock is None:
            lock = threading.Lock()
            _review_locks[ticket_id] = lock
        return lock


def _stored_situation(repository, conversation_id: str, ticket_id: str | None) -> str:
    """This case's last stored summary, or "" - for a review that is GATED, never failed.

    A gate (a held draft, a closed case) is a deterministic decision from local rows that
    says nothing new needs saying. It used to return an empty situation as well, so the
    Case Summary card read "Summary unavailable right now." on a case whose summary was
    sitting in case_reviews - and a closed case therefore looked identical to an exhausted
    quota, which is the one thing that card must be able to distinguish.

    Not called on the llm_error path, and that distinction is the whole point: a FAILED
    call leaves us genuinely without a current summary, so serving the old text unlabelled
    would present stale state as fresh.

    STALENESS IS CHECKED, against the same key the cache itself uses. A gate does not
    freeze the case: while a draft is held the customer can send another message, so the
    stored row can describe fewer turns than the case now has. Measured on the live data
    all five rows were current, which is exactly why this cannot be left to chance - a
    summary that silently omits the newest message is worse than none, and the gate means
    no new one will be generated to replace it.
    """
    if not ticket_id:
        return ""
    try:
        row = repository.get_case_review(ticket_id)
        if not row:
            return ""
        # Scoped to THIS case, the same way case_review scopes its own cache check: the
        # conversation's newest turn may belong to a different case entirely, and comparing
        # against that would blank a perfectly current summary whenever the customer wrote
        # in about something else.
        case_turns = [t for t in repository.list_conversation_turns(conversation_id) or []
                      if t.get("ticket_id") == ticket_id]
        newest = case_turns[-1]["turn_id"] if case_turns else ""
        if not newest or row.get("latest_turn_id") != newest:
            return ""
    except Exception:
        logger.exception("stored_situation_read_failed")
        return ""
    return row.get("situation") or ""


def case_review(repository, conversation_id: str, ticket_id: str | None,
                refresh: bool = False) -> dict:
    """ONE review of ONE case, cached against that case's own newest turn.

    The single LLM call behind all three right-panel cards. It replaces three calls -
    case_summary, case_advice and opportunity_generation - that each re-sent the same
    case: measured 2,821 tokens against 2,062 for this one, a 26% saving that comes almost
    entirely from assembling the context once instead of three times.

    Cached per CASE, which is what makes it cheaper rather than merely tidier. The old
    summary cache was keyed by conversation, so a message on a fraud dispute invalidated
    the summary of an unrelated loan query and re-ran all three calls; here a message on
    case A leaves every other case serving its stored review for nothing.

    Returns the three sections plus, distinctly, WHY a section is empty:
      suppressed   - deliberately silent (a draft is held, or the case is closed)
      llm_error    - the call FAILED. Never to be rendered as "nothing to do".
    A gated or failed review is never written to the cache: a stored empty review cannot
    be told apart from "this case needs nothing", which is the trap that let a 429 cache
    as "no offers" with no way to clear it.
    """
    conversation = repository.get_conversation(conversation_id)
    customer_id = (conversation or {}).get("customer_id") or ""

    ticket = repository.get_ticket(ticket_id) if ticket_id else None
    if ticket is None:
        # Same fallback the route has always used, so a caller that does not know which
        # case it means still gets the conversation's active one.
        active = repository.find_active_ticket(conversation_id)
        ticket = active.model_dump(mode="json") if active else None
        if ticket is None:
            # find_active_ticket EXCLUDES closed tickets - correct for continuity, but it
            # means a conversation whose only case is closed lands here with ticket=None,
            # indistinguishable from one that was never ticketed. The two are opposites:
            # nothing is outstanding on a closed case, and the block below then treats it
            # as an unticketed conversation - no cache key, no lock, and a full LLM review
            # on EVERY render, forever. Measured on the closed claim case: 2,766 prompt
            # tokens per panel paint.
            # Scoped query, not list_tickets(): that loads every ticket in the database on
            # a path that runs on every panel render.
            # The ticket_id, not just a 1: a closed case's stored review is still the
            # correct description of it, and reading it costs nothing. Without the id
            # there is no cache key, so the Case Summary card rendered "unavailable" on a
            # case whose summary was sitting in case_reviews - see _stored_situation.
            with repository.connection() as conn:
                had_ticket = conn.execute(
                    "SELECT ticket_id FROM tickets WHERE conversation_id = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (conversation_id,),
                ).fetchone()
            if had_ticket:
                closed_tid = had_ticket["ticket_id"]
                return {"suppressed": "the case is closed",
                        "situation": _stored_situation(repository, conversation_id, closed_tid),
                        "actions": [], "offers": [], "ticket_id": closed_tid}
    # A conversation with no ticket AT ALL is still reviewed. It has turns, a customer and a
    # sentiment, and the engine this replaces advised on it; refusing here would silently
    # drop the acknowledgement nudge for anyone who has not been ticketed yet.
    tid = ticket["ticket_id"] if ticket else None
    all_turns = repository.list_conversation_turns(conversation_id)
    # THIS case's turns. The old calls were handed the whole conversation - 30 turns across
    # 8 tickets on the live customer - so the model reasoned about a loan enquiry while
    # advising on a fraud dispute.
    # With no ticket there is nothing to scope BY, so the conversation's own turns are the
    # case - which is what they are at that point.
    case_turns = [t for t in all_turns if t.get("ticket_id") == tid] if tid else all_turns
    latest_turn_id = case_turns[-1]["turn_id"] if case_turns else ""

    # GATE FIRST, before the cache and before the lock. check_gates reads only the ticket's
    # status and whether a draft is held - both local rows, no LLM - so a suppressed review
    # must never reach Groq.
    #
    # It used to be checked INSIDE review(), after this function had already decided to
    # generate. A suppressed result is deliberately never cached (a stored empty review
    # cannot be told apart from "this case needs nothing"), so while a draft was held there
    # was no cache row and EVERY render called the LLM again - twice, once per route. That
    # is precisely the window an agent sits in while reviewing a draft. Measured: refreshing
    # with one draft held produced pairs of calls seconds apart, three of them 429s against
    # the 8,000 TPM cap.
    #
    # Fix 174 removed the three-calls-per-opening race; this closes the remaining path,
    # which that fix never reached because a cached reopen holds no draft.
    pending_drafts = repository.list_reply_drafts(
        conversation_id=conversation_id, status="pending")
    gate = case_reviewer.check_gates(ticket=ticket, pending_drafts=pending_drafts)
    if gate:
        # Same shape review() returns when it gates, plus the ticket_id the caller expects.
        #
        # `suppressed` stays set - it is what tells Suggested Actions and Suggested Offers
        # to stay quiet, AND what stops the supersede sweep from retiring this case's
        # recommendation rows on the strength of a review that never ran. Only the
        # situation is filled in: a gate means "nothing NEW to say about this case", not
        # "we no longer know what this case is". The stored summary describes the same
        # turns either way, and serving it is a row read, not an LLM call.
        return {"suppressed": gate, "situation": _stored_situation(repository, conversation_id, tid),
                "actions": [], "offers": [], "ticket_id": tid}

    # The cache is keyed by ticket_id, so a ticketless conversation cannot be cached. It is
    # reviewed every time, which is correct and cheap: it has no case history to re-read.
    # `refresh` is the Refresh button on the Case Summary card - the one caller that means
    # "regenerate", not "show me the current text". Without this the flag was accepted by
    # the route, documented in its docstring, and then dropped: the button returned the
    # cached row and the response labelled it "generated", so it looked like it had worked
    # and had not fired an LLM call in an hour.
    #
    # Safe to force: the write below overwrites the stored row on success, and a failed or
    # suppressed review is still never cached - so a 429 during a manual refresh cannot
    # poison the cache.
    def _cached_row() -> dict | None:
        row = repository.get_case_review(tid) if tid else None
        if row and row.get("latest_turn_id") == latest_turn_id and latest_turn_id:
            return {
                "situation": row.get("situation") or "",
                "actions": row.get("actions") or [],
                "offers": row.get("offers") or [],
                "offers_suppressed": row.get("offers_suppressed"),
                "ticket_id": tid,
                "cached": True,
            }
        return None

    if not refresh:
        hit = _cached_row()
        if hit:
            return hit

    # Hold the case's lock for the generate. Whoever gets here first calls the LLM and
    # writes the cache; the other cards block, and the re-check below then serves them
    # that same row. Without it all three call the LLM - see _review_lock.
    #
    # A ticketless conversation has no key to lock on and no row to cache, so it runs
    # unguarded exactly as before. It is also the cheap case: no case history to re-read.
    if tid:
        lock = _review_lock(tid)
        with lock:
            # Re-check INSIDE the lock. A caller that waited here was almost certainly
            # waiting for the very review it needs, and serving that row is the entire
            # point - a second identical call would be the bug this guards against.
            # `refresh` still forces regeneration, but only for the caller that asked:
            # the Refresh button means "regenerate", and it holds the lock while it does.
            if not refresh:
                hit = _cached_row()
                if hit:
                    return hit
            return _generate_case_review(
                repository, conversation_id, customer_id, ticket, tid,
                case_turns, all_turns, latest_turn_id,
            )

    return _generate_case_review(
        repository, conversation_id, customer_id, ticket, tid,
        case_turns, all_turns, latest_turn_id,
    )


def _generate_case_review(repository, conversation_id: str, customer_id: str,
                          ticket: dict | None, tid: str | None,
                          case_turns: list[dict], all_turns: list[dict],
                          latest_turn_id: str) -> dict:
    """The LLM call and its cache write. Split out of case_review so the lock above can
    wrap it without duplicating the body on the locked and unlocked paths."""
    pending_drafts = repository.list_reply_drafts(
        conversation_id=conversation_id, status="pending")
    graph_context = _graph_context_for(repository, customer_id)
    # Sentiment stays CUSTOMER-wide, read from the whole conversation: how someone feels is
    # not compartmentalised by case, and the right panel reports it the same way.
    sentiment = _recent_sentiment(all_turns)

    result = case_reviewer.review(
        generator=_review_generator(),
        ticket=ticket,
        turns=case_turns,
        graph_context=graph_context,
        sentiment=sentiment,
        pending_drafts=pending_drafts,
        charges=graph_context.get("charges"),
        all_turns=all_turns,
    )
    result["ticket_id"] = tid
    # Only a successful review of a real case is stored. `tid` is None for a conversation
    # with no ticket yet, and case_reviews is keyed by ticket_id with a foreign key to
    # tickets, so writing that row would raise rather than cache anything.
    if tid and not result.get("llm_error") and not result.get("suppressed"):
        repository.save_case_review(tid, conversation_id, latest_turn_id, result)
    return result


@router.get("/next-best-actions")
def get_next_best_actions(conversation_id: str, ticket_id: str | None = None) -> dict:
    """What needs saying to this customer, decided by the LLM (see case_advisor).

    Replaces four hardcoded `if` rules that only ever fired on situations somebody had
    anticipated in advance. Those rules also had no UI for their whole life, so none of
    them was ever seen by anyone.
    """
    repository = get_repository()
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    customer_id = conversation.get("customer_id") or ""

    ticket = repository.get_ticket(ticket_id) if ticket_id else None
    if ticket is None:
        active = repository.find_active_ticket(conversation_id)
        ticket = active.model_dump(mode="json") if active else None

    turns = repository.list_conversation_turns(conversation_id)
    pending_drafts = repository.list_reply_drafts(
        conversation_id=conversation_id, status="pending")

    # Same degrade-gracefully graph lookup the offers route uses: no Neo4j means no
    # customer records in the prompt, not an error.
    graph_context = _graph_context_for(repository, customer_id)
    sentiment = _recent_sentiment(turns)
    promise = {
        "due_at": (ticket or {}).get("follow_up_due_at"),
        "overdue": _promise_overdue(ticket),
    }

    # ONE review of this case now feeds all three right-panel cards - the situation, these
    # actions, and the offers below. It replaces three separate calls that each re-sent the
    # same case (2,821 tokens against 2,062, measured), and it is cached per CASE, so a
    # message on one of the customer's cases no longer regenerates the others.
    #
    # The generator seam lives inside case_review (_review_generator) for the same reason it
    # lived here before: CI has no API key, and a route that reaches GroqGenerator() directly
    # is untestable. The fix belongs in the route, not in a weakened assertion.
    advice = case_review(repository, conversation_id, (ticket or {}).get("ticket_id"))
    llm_error = advice.get("llm_error")
    suppressed = advice.get("suppressed")

    pending = repository.list_agent_assist_recommendations(conversation_id=conversation_id, status="pending")
    # THIS CASE's rows only, for the two decisions below. `pending` stays conversation-wide
    # because it is also the response body, and conversation-level rows (an offer, which
    # carries no ticket_id) belong there - but a decision about one case must never read
    # another case's rows.
    #
    # One conversation holds several cases: this customer has two fraud disputes in
    # conv_6c8c88e59ca5. Keyed on the conversation, `existing_by_type` matched the OTHER
    # case's acknowledgement, so this case's acknowledgement took the refresh branch below,
    # overwrote that case's text, and never created a row of its own - the card rendered
    # empty while the LLM had produced the nudge correctly. The sweep had the same flaw in
    # reverse: one case's review could retire another case's nudges.
    _case_id = (ticket or {}).get("ticket_id")
    case_pending = [row for row in pending if row.get("ticket_id") == _case_id] if _case_id else pending
    # Keyed by type, and it has to be: one live nudge per type per case. The engine re-reads
    # the case on every render, so the same TYPE legitimately recurs with different words -
    # a promise whose deadline has moved after the agent sent an update.
    existing_by_type = {row["action_type"]: row for row in case_pending}
    for action in advice.get("actions", []):
        prior = existing_by_type.get(action["action_type"])
        if prior is not None:
            # REFRESH, never skip. `continue` here froze the first nudge of each type: the
            # freshly generated text was discarded on arrival and the stale row stayed on
            # screen, so the card told the agent "nothing sent since we promised it" one
            # minute AFTER they had sent it. The sweep below could not save it either -
            # it also compares action_type, so a new promise nudge protected the old one.
            # `prior` is passed so a refresh that carries no draft keeps the one already on
            # the row: refresh_agent_assist_recommendation REPLACES metadata_json wholesale,
            # so without this a single review that omitted the field would silently blank a
            # good draft and the card would fall back to the generic template.
            refreshed = repository.refresh_agent_assist_recommendation(
                prior["recommendation_id"],
                reason=action["reason"],
                confidence=action["confidence"],
                metadata=_action_metadata(action, ticket, prior=prior),
            )
            if refreshed is not None:
                prior.update(refreshed)
            continue
        pending.append(repository.add_agent_assist_recommendation(
            conversation_id=conversation_id,
            customer_id=customer_id,
            ticket_id=(ticket or {}).get("ticket_id"),
            action_type=action["action_type"],
            reason=action["reason"],
            confidence=action["confidence"],
            priority=0,
            # follow_up_due_at travels with the row so the CARD can compute the countdown
            # live on every render. The reason sentence carries the absolute date only
            # ("13 Sep, 10:21pm") because it is written once and read later - a stored
            # "8h left" is wrong by morning. Deadline is data; time remaining is derived.
            #
            # ONLY on a promise action. Attached to every action it rendered "7h left"
            # beside "CUSTOMER UPSET", which has no deadline of its own - a countdown
            # borrowed from a different fact, which is worse than no countdown at all.
            metadata=_action_metadata(action, ticket),
        ))

    # RETIRE what the rules no longer produce. The loop above only ever ADDED, so a row
    # outlived the condition that created it: measured on the live board, the follow-up
    # nudge was still on screen after the follow-up had been sent, because the rule had
    # correctly stopped firing while the row it wrote minutes earlier sat in the table
    # forever. The card reads the table, not the rules.
    #
    # Scoped to the action types THIS engine owns. /next-best-actions returns every pending
    # row for the conversation, offers included, and the NBA engine does not produce offers
    # - so an unscoped sweep would retire live cross-sell rows that nothing had decided.
    #
    # Only ever runs on a SUCCESSFUL engine pass. recommend() raising would leave `result`
    # unbound and this block unreached; an engine that returns nothing because it FAILED
    # must never be read as "nothing is outstanding" and erase the queue - the same failure
    # mode as a 429 cached as "no offers".
    #
    # SKIPPED ENTIRELY when the call failed or was gated. An engine that returned nothing
    # because it FAILED must never be read as "nothing is outstanding" - that would let one
    # rate-limited call silently empty a queue of real work, which is the trap recorded in
    # ec2-operations.md where a 429 cached as "no offers" and Refresh could not clear it.
    if not llm_error and not suppressed:
        still_current = {a["action_type"] for a in advice.get("actions", [])}
        # case_pending, not pending: this review describes ONE case, so it is only evidence
        # about that case's rows. Sweeping the whole conversation let a review of case A
        # retire case B's nudges purely because B's type was absent from A's actions.
        for row in case_pending:
            action_type = row["action_type"]
            if (action_type in _OFFER_ACTION_TYPES
                    or action_type in PIPELINE_ACTION_TYPES
                    or action_type in still_current):
                continue
            repository.update_agent_assist_recommendation(
                row["recommendation_id"], status="superseded", actor="system",
            )
            row["status"] = "superseded"
    pending = [row for row in pending if row.get("status") == "pending"]

    # Do not surface recommendations tied to a ticket that is no longer active (resolved/
    # closed). A previously-saved 'pending' row lingers after its ticket is resolved; a done
    # ticket has no live action to take, so hide it. Conversation-level rows (no ticket_id)
    # are unaffected.
    # A close PROPOSAL the customer's own words raised. Written into the same table as the
    # advisor's nudges so it inherits the card, the decision route, the status column and
    # the audit trail; the permanent record of what the customer said lives on the ticket
    # itself (ticket_events, written by graph.py _propose_close) and is never rewritten.
    _sync_close_proposals(repository, conversation_id, customer_id, ticket, pending)

    _terminal = {"closed"}
    _ticket_status: dict[str, str | None] = {}

    def _is_active(ticket_id: str | None) -> bool:
        if not ticket_id:
            return True
        if ticket_id not in _ticket_status:
            t = repository.get_ticket(ticket_id)
            _ticket_status[ticket_id] = (t or {}).get("status")
        return _ticket_status[ticket_id] not in _terminal

    pending = [row for row in pending if _is_active(row.get("ticket_id"))]

    return {
        "conversation_id": conversation_id,
        "customer_id": customer_id,
        "ticket_id": (ticket or {}).get("ticket_id"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # Three distinct states, so the card can say which: items, deliberate silence, or
        # a failure. Rendering a failure as an empty list is what makes a broken check look
        # like a clean case.
        "suppressed": suppressed,
        "llm_error": llm_error,
        # Scoped to the case the caller asked for. `pending` is deliberately
        # conversation-wide (it carries the offers, which have no ticket_id), and the
        # actions were returned straight out of it - so opening a customer's SECOND case
        # showed the FIRST one's nudges. Measured on Fathima: asking for the loan case
        # returned three nudges all belonging to the transaction dispute, while the Case
        # Summary beside them correctly described the loan.
        #
        # A case's card shows THAT CASE'S rows and nothing else. Rows with no ticket_id
        # used to be kept here as well, for two reasons that were both checked and are
        # both false:
        #
        #   - "the close proposals _sync_close_proposals writes have none" - it passes
        #     ticket_id=ticket_id and returns early when there is no ticket, so a close
        #     proposal ALWAYS carries its case.
        #   - "an unticketed conversation's nudges" - there is no such conversation. Since
        #     the ticket redesign a ticket is the name of a matter and is created for every
        #     query: TicketDecision is built with `required=True` hardcoded
        #     (orchestration_agents.py:653, "a ticket is a grouping id: always") at both of
        #     its call sites, so decide_ticket can never route to skip_ticket. And a
        #     conversation that genuinely had no case would have _case_id None and be served
        #     by the `not _case_id` branch anyway.
        #
        # So the clause could only ever fire WITH a case on screen, which is exactly when a
        # case-less row does not belong there. Measured on the live customer: an
        # information_needed nudge about claim CLM001003 - a document request on her CLOSED
        # claim case - rendered on a general_inquiry case about her credit card interest
        # rate, beside a Case Summary that correctly described only the interest rate.
        "actions": [r for r in pending
                    if r.get("action_type") not in _OFFER_ACTION_TYPES
                    and (not _case_id or r.get("ticket_id") == _case_id)],
    }


def _sync_close_proposals(repository, conversation_id: str, customer_id: str,
                          ticket: dict | None, pending: list[dict]) -> None:
    """Surface a customer-raised close proposal as a decidable work item.

    The customer's words are recorded permanently on the ticket (ticket_events, written by
    graph.py _propose_close) and that record is never rewritten. This creates the matching
    work item in agent_assist_recommendations, which is what the card renders and the
    decision route acts on - the table that already has a status column, an audit trail and
    a decision endpoint. The event log has none of those: nothing in this codebase reads it
    to decide state, so a proposal living only there could never be marked handled and
    would reappear on every refresh forever.

    ONE row per proposing message. A second "thanks" on a case an agent already said "not
    yet" to must not resurrect the card: any decided row for this ticket whose proposal is
    no older than the decision means the agent has already answered this question.
    """
    if not ticket:
        return
    ticket_id = ticket.get("ticket_id")
    # Serviceable only. A `logged` ticket is a grouping id - closing it is a no-op, so
    # proposing a close on one is work nobody asked for. _propose_close applies the same
    # rule, but the card must not depend on that having held.
    if not ticket_id or ticket.get("status") not in SERVICEABLE_TICKET_STATUSES:
        return

    events = [e for e in repository.list_ticket_events(ticket_id)
              if e.get("event_type") == "close_proposed"]
    if not events:
        return
    latest = events[-1]

    existing = repository.list_agent_assist_recommendations(ticket_id=ticket_id)
    for row in existing:
        if row.get("action_type") != ActionType.READY_TO_CLOSE.value:
            continue
        # Still open on the card - nothing to add.
        if row.get("status") == "pending":
            return
        # Already answered. Only a proposal NEWER than that answer reopens the question,
        # which is what lets a customer confirm again after an agent said "not yet".
        decided_at = row.get("decided_at") or ""
        if (latest.get("created_at") or "") <= decided_at:
            return

    details = latest.get("details") or {}
    quoted = (details.get("customer_message") or "").strip()
    reason = (f'Customer replied "{quoted[:160]}" — their case may be finished.'
              if quoted else "The customer's last message suggests their case is finished.")

    created = repository.add_agent_assist_recommendation(
        conversation_id=conversation_id,
        customer_id=customer_id,
        ticket_id=ticket_id,
        action_type=ActionType.READY_TO_CLOSE.value,
        reason=reason,
        # Not a model's confidence: the detector's, and it is not a probability. Held below
        # the advisor's own scores so a proposal never outranks a promise we have broken.
        confidence=0.6,
        priority=0,
        # No CRM or approval state travels with this row, deliberately. A failed CRM sync is
        # connector health and belongs in System Configuration - the closing agent cannot
        # fix Jira and it says nothing about whether the customer's problem is solved. And
        # `approval_status` is dormant: it is written once at ticket creation for five
        # intents, the only thing that can change it (POST /tickets/{id}/approval) is called
        # by nothing in the UI, and no gate anywhere reads it. Showing "approval pending"
        # would assert a sign-off process that does not exist - the same defect as telling a
        # customer "the fraud team is reviewing" when no case had been created.
        metadata={
            "basis": f"Customer message on {latest.get('created_at', '')[:10]}",
            "proposed_at": latest.get("created_at"),
        },
    )
    pending.append(created)


# What the HUMAN must supply, per nudge type. Every drafted nudge gets one.
#
# This is the point of the card. A nudge exists because a person has to DO something - the
# page it feeds was built because "we told a customer something false": the AI wrote "the
# fraud team is reviewing" while that ticket's CRM sync had failed. If the model writes the
# whole message and the agent only clicks Send, the human-in-the-loop gap is back and
# approving a nudge is forwarding an AI message.
#
# So the LLM supplies the FACTS (loan ids, amounts, dates - it does this well) and the
# bracket is where the judgement goes. Named per type, because each owes something
# different: a promise owes the update, a warning owes what we are doing about it.
_REQUIRED_BRACKET = {
    ActionType.PROMISED_UPDATE.value:
        "[Add the update we promised - what has actually happened since.]",
    ActionType.PROACTIVE_WARNING.value:
        "[State what we are doing about this, or what they should do next.]",
    ActionType.INFORMATION_NEEDED.value:
        "[Name exactly what is outstanding and how they should send it.]",
    ActionType.ACKNOWLEDGEMENT.value:
        "[Say what you are doing about it before sending.]",
    "cross_sell": "[Confirm the terms and why this customer, before sending.]",
    "up_sell": "[Confirm the terms and why this customer, before sending.]",
}

# A bracket the model wrote itself - any [....] on its own line.
_HAS_BRACKET = re.compile(r"\[[^\]]{10,}\]")


def _ensure_bracket(draft_text: str, action_type: str) -> str:
    """Guarantee the agent has something to fill in. Never trusted to the prompt.

    The DRAFT contract asks for a bracket only where one is needed, and the model duly
    decided a complete-looking warning needed none - "Please ensure timely payment to avoid
    further penalties", ready to send, no human judgement anywhere in it. A prompt rule is a
    request; this is the guarantee.

    A bracket the model wrote itself is kept: it already names what is missing, in the
    context of the message it wrote.
    """
    text = (draft_text or "").strip()
    if not text or _HAS_BRACKET.search(text):
        return text
    bracket = _REQUIRED_BRACKET.get(action_type)
    if not bracket:
        return text
    # Before the sign-off when there is one, so the message does not end mid-instruction.
    lines = text.split("\n\n")
    if len(lines) > 1 and lines[-1].lower().startswith("thank you"):
        lines.insert(-1, bracket)
    else:
        lines.append(bracket)
    return "\n\n".join(lines)


def _greeting(repository, customer_id: str) -> str:
    """"Hi <their name>," for a fallback draft - the same opening the LLM drafts use.

    The fallback templates used to start "Hello,". That put two different greetings on the
    same card depending only on whether the model had written that particular draft: an
    LLM draft said "Hi Fathima Devasahayam," and the template beside it said "Hello,".
    """
    name = ""
    if customer_id:
        # There is no repository.get_customer(); the display_name lives on `customers` and
        # is the right source here - it is populated for an unregistered sender (Neha) where
        # the graph record is None, and _salutation turns a bare email into "Customer".
        with repository.connection() as conn:
            row = conn.execute(
                "SELECT display_name FROM customers WHERE customer_id = ?", (customer_id,)
            ).fetchone()
        name = (row["display_name"] if row else "") or ""
    return f"Hi {_salutation(name)},"


def _action_metadata(action: dict, ticket: dict | None, prior: dict | None = None) -> dict:
    """What travels with a recommendation row.

    The promise deadline goes ONLY on the action that is about the promise. Everything
    else gets `basis` alone, so the card shows a countdown exactly where one applies.

    `prior` is the existing row on a refresh. It exists only to carry a stored draft
    forward when the new review did not write one - see the call site.
    """
    metadata = {"basis": action.get("basis")}
    # The customer-facing message the review wrote for this action. Carried in `metadata`
    # rather than a new column deliberately: add_agent_assist_recommendation takes a fixed
    # parameter list, so an unlisted field would be dropped with a successful-looking write
    # - the trap that nearly killed migration 020. metadata is already a free-form JSON
    # blob both the add and refresh paths persist, so nothing else has to change.
    #
    # The new draft when there is one, else whatever the row already held. A review that
    # omits the field must never blank a good draft - refresh replaces metadata_json whole.
    draft = action.get("draft") or (prior or {}).get("metadata", {}).get("draft")
    if draft:
        metadata["draft"] = draft
    if action["action_type"] in DRAFTABLE_ACTION_TYPES and (ticket or {}).get("follow_up_due_at"):
        metadata["follow_up_due_at"] = ticket["follow_up_due_at"]
    return metadata


def _graph_context_for(repository, customer_id: str) -> dict:
    """The customer's BFSI records, or {} when the graph is unreachable."""
    if not customer_id:
        return {}
    client = _try_neo4j()
    if not client:
        return {}
    try:
        from services.neo4j_service.queries import (
            get_customer_by_id, get_customer_by_identifier, get_customer_context_by_id,
        )
        for row in repository.list_customer_identifiers(customer_id):
            found = (get_customer_by_id(client, row["identifier"])
                     if row["channel"] == "graph"
                     else get_customer_by_identifier(client, row["identifier"]))
            if found:
                return get_customer_context_by_id(client, found["customer_id"]) or {}
    except Exception as exc:
        logger.warning("case_advice_graph_lookup_failed customer=%s: %s", customer_id, exc)
    return {}


def _recent_sentiment(turns: list[dict]) -> str | None:
    """Sentiment over the last five inbound turns, as the right panel reports it.

    Read from the sentiment already stored on each turn by the intent classifier - not
    re-derived here, so the card and the panel beside it cannot disagree.
    """
    inbound = [t for t in turns if t.get("direction") == "inbound"][-5:]
    if not inbound:
        return None
    negative = sum(1 for t in inbound
                   if ((t.get("metadata") or {}).get("sentiment") or "").lower() == "negative")
    if not negative:
        return "neutral or positive"
    pct = round(negative / len(inbound) * 100)
    label = "very frustrated" if pct >= 60 else "some frustration"
    return f"{label} ({pct}% negative across the last {len(inbound)} messages)"


def _promise_overdue(ticket: dict | None) -> bool:
    due_at = (ticket or {}).get("follow_up_due_at")
    if not due_at:
        return False
    try:
        return datetime.now(timezone.utc) > datetime.fromisoformat(due_at)
    except (TypeError, ValueError):
        return False


@router.get("/opportunities")
def get_opportunities(conversation_id: str, ticket_id: str | None = None) -> dict:
    """Cross-sell/up-sell opportunities for a conversation (LLM-selected from a
    code-built candidate set, code-gated; see opportunity_engine). Persists new
    items as pending agent_assist_recommendations rows; returns pending rows.
    """
    repository = get_repository()
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    customer_id = conversation.get("customer_id") or ""

    # Same resolution the other two cards use. The browser has always sent ticket_id here
    # (focusedCaseParam, app.js), but this signature did not accept it, so FastAPI dropped
    # it and the call below passed None - and case_review cannot read OR write its cache
    # without a ticket_id. This card therefore made a guaranteed LLM call on every render,
    # while its own comment said the offers come from the same one review as the other two.
    ticket = repository.get_ticket(ticket_id) if ticket_id else None
    if ticket is None:
        active = repository.find_active_ticket(conversation_id)
        ticket = active.model_dump(mode="json") if active else None

    def _pending_offers() -> list[dict]:
        rows = repository.list_agent_assist_recommendations(
            conversation_id=conversation_id, status="pending")
        return [r for r in rows if r.get("action_type") in _OFFER_ACTION_TYPES]

    # Resolve the BFSI graph customer + context (same degrade-gracefully pattern
    # as the NBA engine — no Neo4j means no candidates, not an error).
    client = _try_neo4j()
    customer: dict = {}
    graph_context: dict = {}
    charges: list[dict] = []
    if client and customer_id:
        try:
            from services.neo4j_service.queries import (
                get_charges, get_customer_by_id, get_customer_by_identifier,
                get_customer_context_by_id,
            )
            for row in repository.list_customer_identifiers(customer_id):
                found = (get_customer_by_id(client, row["identifier"])
                         if row["channel"] == "graph"
                         else get_customer_by_identifier(client, row["identifier"]))
                if found:
                    customer = found
                    graph_context = get_customer_context_by_id(client, found["customer_id"]) or {}
                    charges = get_charges(client, found["customer_id"]) or []
                    break
        except Exception as exc:
            logger.warning("opportunity_graph_lookup_failed conv=%s: %s", conversation_id, exc)
    if not graph_context:
        return {"conversation_id": conversation_id, "customer_id": customer_id,
                "suppressed": None, "opportunities": _pending_offers()}

    # Conversation-side inputs. list_customer_turns returns newest-first; the
    # engine (and its prompt) expect chronological order — normalize here.
    # SERVICEABLE only. len(tickets) feeds the cache fingerprint below, so counting LOGGED
    # ids - which the redesign now creates for EVERY customer query - would change the
    # fingerprint on every message and re-run the engine's ~1000-token LLM call on the next
    # render. check_gates takes the list but does not read it (sentiment-only since
    # 2026-07-23), so this only affects the fingerprint and the engine's own ticket view.
    tickets = [
        t for t in repository.list_tickets()
        if t.get("customer_id") == customer_id
        and str(t.get("status") or "").lower() in SERVICEABLE_TICKET_STATUSES
    ]
    turns = list(reversed(repository.list_customer_turns(customer_id)))

    # "Do not repeat": every offer already suggested for this conversation,
    # whatever its decision — a dismissed offer stays retired.
    all_rows = repository.list_agent_assist_recommendations(conversation_id=conversation_id)
    suggested_products = {
        (r.get("metadata") or {}).get("product")
        for r in all_rows if r.get("action_type") in _OFFER_ACTION_TYPES
    } - {None}
    already_suggested = [
        f"{(r.get('metadata') or {}).get('product')}: {r.get('reason') or ''}"
        for r in all_rows if r.get("action_type") in _OFFER_ACTION_TYPES
    ]

    # Cache guard. This endpoint is called on EVERY right-panel render, including the
    # inbox poll's, and the engine's LLM call costs ~1000 tokens whether or not it finds
    # anything - measured at 53 calls in one day with zero customer messages. Re-run only
    # when something that could change the answer has changed: the customer's graph
    # records, how many turns they have, or which offers were already suggested.
    # `gate` is IN the fingerprint, and has to be: it is the one input that decides whether
    # offers appear at all, and without it a mood change could not invalidate this cache.
    # Everything else here is holdings, counts and products - none of which move when a
    # customer calms down. Measured on the live customer: the gate stopped suppressing her
    # offers, case_reviews recorded the offer correctly, and this row still answered
    # "recent negative sentiment" from before the change, because its inputs were all
    # unchanged. The card cannot be more current than the coarsest key in its path.
    fingerprint = json.dumps(
        {"graph": graph_context, "turns": len(turns), "tickets": len(tickets),
         "suggested": sorted(already_suggested),
         "gate": case_reviewer.offers_suppressed(turns)},
        sort_keys=True, default=str,
    )
    input_hash = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    cached = repository.get_opportunity_evaluation(conversation_id)
    if cached and cached.get("input_hash") == input_hash:
        # Already evaluated on these exact inputs. Serve what it produced - which is
        # legitimately nothing when the model found no offer worth making.
        if cached.get("suppressed"):
            return {"conversation_id": conversation_id, "customer_id": customer_id,
                    "suppressed": cached["suppressed"], "opportunities": []}
        return {"conversation_id": conversation_id, "customer_id": customer_id,
                "suppressed": None, "opportunities": _pending_offers()}

    # Offers come from the SAME review that produced this case's summary and actions -
    # one call, not a second one on the same conversation. The fingerprint cache above is
    # kept: it answers "have these inputs already been evaluated", which is a different
    # question from the per-case cache inside case_review, and removing it would change
    # when offers refresh for reasons that have nothing to do with this merge.
    #
    # The offers section carries its own suppression reason (negative sentiment gates
    # selling, while actions deliberately still fire), so it is mapped onto the shape this
    # route has always returned.
    review = case_review(repository, conversation_id, (ticket or {}).get("ticket_id"))
    result = {
        "opportunities": review.get("offers") or [],
        "suppressed": review.get("offers_suppressed") or review.get("suppressed"),
    }
    if review.get("llm_error"):
        # A failed review must never read as "no offers worth making" - that is the trap
        # recorded in ec2-operations.md, where a 429 cached as empty and Refresh could not
        # clear it. Serve whatever is already pending and record nothing.
        return {"conversation_id": conversation_id, "customer_id": customer_id,
                "suppressed": None, "opportunities": _pending_offers()}

    # Record that this evaluation ran, whatever it produced — including nothing. Without
    # this the no-offer case leaves no trace and re-runs on every render forever.
    try:
        repository.save_opportunity_evaluation(
            conversation_id, input_hash, result.get("suppressed"))
    except Exception:
        logger.exception("opportunity_evaluation_save_failed")  # serve it anyway

    if result.get("suppressed"):
        return {"conversation_id": conversation_id, "customer_id": customer_id,
                "suppressed": result["suppressed"], "opportunities": []}

    # Persist new items; dedupe by product against EVERY prior row (pending,
    # approved, dismissed) so nothing resurfaces after a decision.
    for opp in result.get("opportunities") or []:
        if opp["product"] in suggested_products:
            continue
        repository.add_agent_assist_recommendation(
            conversation_id=conversation_id,
            customer_id=customer_id,
            ticket_id=None,
            action_type=opp["kind"],
            reason=opp["pitch"],
            confidence=opp["confidence"],
            priority=5,
            # `draft` is the customer-facing offer message; `reason` above is the 20-word
            # pitch the CARD shows the agent. They are different audiences and the offer
            # draft used to send the pitch verbatim - a card fragment, with no greeting.
            metadata={"product": opp["product"], "basis": opp["basis"],
                      "why_now": opp["reason"], "source": "opportunity_engine",
                      **({"draft": opp["draft"]} if opp.get("draft") else {})},
        )

    return {"conversation_id": conversation_id, "customer_id": customer_id,
            "suppressed": None, "opportunities": _pending_offers()}


@router.get("/recommendations")
def list_recommendations(ticket_id: str | None = None, conversation_id: str | None = None) -> list[dict]:
    return get_repository().list_agent_assist_recommendations(
        ticket_id=ticket_id, conversation_id=conversation_id,
    )


# THE FALLBACK. The review now writes the message itself (case_reviewer's DRAFT contract)
# and _build_nudge_draft prefers it; these templates are what a row gets when the model
# omitted the draft or it failed validation.
#
# They are kept, rather than deleted, because they degrade honestly: a generic opener plus
# a visible bracket is obviously unfinished, whereas an empty draft card looks broken and a
# silently generic one looks finished when it is not.
#
# The history behind them still matters. Probed against the live fraud case, a model asked
# for this sentence wrote "I have blocked your debit card immediately" when we had told the
# customer to block it themselves and the CRM sync had failed - which is why the card
# advised and never drafted (commit 6d7977d). That request carried no contract; the DRAFT
# rules now forbid stating anything about our side of the work, and the agent reviews every
# draft before it is sent.
_ACK_OPENERS = {
    ActionType.ACKNOWLEDGEMENT.value: (
        "I am sorry this has been frustrating, and thank you for bearing with us.\n\n"
        "I can see {subject} (reference {reference}) is still open.\n\n"
        "[Say what you are doing about it before sending.]"
    ),
    ActionType.INFORMATION_NEEDED.value: (
        "I am writing about {subject} (reference {reference}).\n\n"
        "To move this forward we still need something from you.\n\n"
        "[Name exactly what is outstanding before sending.]"
    ),
    ActionType.PROACTIVE_WARNING.value: (
        "I am getting in touch about {subject} (reference {reference}) before it "
        "affects you.\n\n"
        "[State what you found in their records, and what they can do about it, "
        "before sending.]"
    ),
}


def _build_nudge_draft(repository, recommendation: dict) -> dict:
    """An editable draft for a nudge whose answer is a message to the customer.

    Same shape as _build_follow_up_draft and the same reasons: reply on the channel the
    customer used, thread onto their last inbound turn, and assemble the text from the
    record rather than generating it - an LLM call here would spend the binding Groq limit
    restating facts we already hold, and inventing the part we do not.

    Before this, approving one of these three flipped a status column and wrote an audit
    row - nothing reached the customer. The card's own prompt calls every one of them "a
    reason to WRITE to the customer", and not one of them could produce a message.
    """
    action_type = recommendation.get("action_type") or ""
    conversation_id = recommendation.get("conversation_id") or ""
    ticket_id = recommendation.get("ticket_id")
    ticket = repository.get_ticket(ticket_id) if ticket_id else None

    turns = repository.list_conversation_turns(conversation_id)
    inbound = [t for t in turns if t.get("direction") == "inbound"]
    last_inbound = inbound[-1] if inbound else None
    channel = (last_inbound or {}).get("channel") or "web_chat"

    # The review's own draft, written against this customer's records and already greeting
    # them by name. Falls back to the template when the model omitted it or _clean_draft
    # rejected it - see the note above _ACK_OPENERS.
    draft_text = (recommendation.get("metadata") or {}).get("draft") or ""
    if not draft_text:
        subject = (ticket or {}).get("title") or "your request"
        reference = ticket_id or conversation_id
        opener = _ACK_OPENERS[action_type].format(
            subject=subject.lower(), reference=reference)
        draft_text = (_greeting(repository, recommendation.get("customer_id") or "")
                      + "\n\n" + opener + "\n\nThank you for your patience.")
    # Applied to BOTH paths: the model's draft may have no bracket, and a template's bracket
    # is already counted by _HAS_BRACKET, so this neither duplicates nor misses one.
    draft_text = _ensure_bracket(draft_text, action_type)

    return repository.add_reply_draft(
        conversation_id=conversation_id,
        customer_id=recommendation.get("customer_id") or "",
        channel=channel,
        draft_text=draft_text,
        ticket_id=ticket_id,
        inbound_turn_id=(last_inbound or {}).get("turn_id"),
        hold_reason="Approved nudge - edit & send",
        reason_code=action_type,
        channel_identifier=None,
        provider="nudge_reply",
        # Lets a discard of this draft put the recommendation back to `pending`.
        recommendation_id=recommendation.get("recommendation_id"),
    )


def _build_follow_up_draft(repository, recommendation: dict) -> dict:
    """Create an editable follow-up draft grounded in what we actually promised.

    The text is assembled from the record rather than generated: the promise itself is in
    the reply we already sent, the ticket carries the case, and an LLM call here would cost
    requests against the binding Groq limit to restate facts we hold. The agent edits it in
    the same draft card they already use, so the wording is theirs before it is sent.
    """
    conversation_id = recommendation.get("conversation_id") or ""
    ticket_id = recommendation.get("ticket_id")
    ticket = repository.get_ticket(ticket_id) if ticket_id else None

    # Reply on the channel the customer used, threaded onto their last inbound message.
    turns = repository.list_conversation_turns(conversation_id)
    inbound = [t for t in turns if t.get("direction") == "inbound"]
    last_inbound = inbound[-1] if inbound else None
    channel = (last_inbound or {}).get("channel") or "web_chat"

    # The review's own draft first, same as _build_nudge_draft. A promised_update still
    # carries a bracket in practice - the update we owe is a decision, not a record - but
    # the rest of the message names the case and its real facts instead of "your request".
    draft_text = (recommendation.get("metadata") or {}).get("draft") or ""
    if not draft_text:
        subject = (ticket or {}).get("title") or "your request"
        reference = ticket_id or conversation_id
        draft_text = (
            _greeting(repository, recommendation.get("customer_id") or "") + "\n\n"
            f"I am following up on {subject.lower()} (reference {reference}), which we told you "
            "we would come back to you about.\n\n"
            "[Add the update here before sending.]\n\n"
            "Thank you for your patience."
        )
    draft_text = _ensure_bracket(
        draft_text, recommendation.get("action_type") or ActionType.PROMISED_UPDATE.value)
    return repository.add_reply_draft(
        conversation_id=conversation_id,
        customer_id=recommendation.get("customer_id") or "",
        channel=channel,
        draft_text=draft_text,
        ticket_id=ticket_id,
        inbound_turn_id=(last_inbound or {}).get("turn_id"),
        hold_reason="Promised follow-up — edit & send",
        reason_code=recommendation.get("action_type") or ActionType.PROMISED_UPDATE.value,
        channel_identifier=None,
        provider="follow_up_nudge",
        recommendation_id=recommendation.get("recommendation_id"),
    )


@router.post("/recommendations/{recommendation_id}/decision")
def decide_recommendation(recommendation_id: str, payload: NBADecisionUpdate) -> dict:
    repository = get_repository()
    existing = repository.get_agent_assist_recommendation(recommendation_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    # Approving an OFFER executes something: it creates an editable reply draft
    # (the existing HIL draft-card flow) that the agent reviews and sends — the
    # send then delivers to every push channel (WhatsApp/email) on record.
    # Validate preconditions BEFORE flipping the recommendation status.
    draft = None
    if payload.status == "approved" and existing.get("action_type") in _OFFER_ACTION_TYPES:
        conversation_id = existing.get("conversation_id") or ""
        customer_id = existing.get("customer_id") or ""
        # PUSH channels only - whatsapp or email. An offer is a message to someone who is
        # not currently looking at the portal, so web chat does not qualify: delivery.py
        # has no outbound provider for it and the offer would sit unread until the
        # customer happened to visit. test_approve_offer_fails_without_push_channel holds
        # this rule: a web-chat-only customer cannot be sent an offer at all.
        #
        # Same resolver the send uses (customer RECORD + channels written in from), then
        # narrowed here, so the two cannot disagree about WHERE someone is reachable -
        # only about which of those places an offer may use.
        from apps.api.routes.reply_drafts import reachable_push_identities
        push = [i for i in reachable_push_identities(repository, customer_id)
                if i.get("channel") in ("whatsapp", "email")]
        if not push:
            raise HTTPException(
                status_code=400,
                detail="Customer has no WhatsApp or email on record to deliver an offer.")
        pending_drafts = repository.list_reply_drafts(
            conversation_id=conversation_id, status="pending")
        if pending_drafts:
            raise HTTPException(
                status_code=409,
                detail="A pending reply draft already exists — send or discard it first.")
        # Carry the offer's product (health_insurance, credit_card, …) onto the
        # draft so the sent offer turn can be grouped by its own theme in the
        # conversation view (matching topic group, else its own group).
        offer_product = (existing.get("metadata") or {}).get("product")
        # The review's offer message. Falls back to the pitch wrapped in a greeting - the
        # pitch ALONE used to be the whole draft ("Get a credit card with rewards and zero
        # annual fee"), which is a card fragment written for the agent, sent to a customer
        # with no greeting, no context and no sign-off.
        offer_draft = (existing.get("metadata") or {}).get("draft") or ""
        if not offer_draft:
            offer_draft = (
                _greeting(repository, customer_id) + "\n\n"
                + (existing.get("reason") or "")
                + "\n\n[Add anything else they should know before sending.]\n\n"
                "Thank you for banking with us."
            )
        offer_draft = _ensure_bracket(offer_draft, existing.get("action_type") or "cross_sell")
        draft = repository.add_reply_draft(
            conversation_id=conversation_id,
            customer_id=customer_id,
            channel=OFFER_DRAFT_CHANNEL,
            draft_text=offer_draft,  # editable by the agent before it goes
            hold_reason="Approved offer — review & send",
            reason_code=existing.get("action_type") or "cross_sell",
            channel_identifier=None,
            provider="opportunity_engine",
            offer_product=offer_product,
            recommendation_id=recommendation_id,
        )

    # Approving a FOLLOW-UP also executes something: an editable draft in the conversation's
    # OWN thread. Deliberately not the offer path - an offer fans out to every push channel
    # on record, whereas a follow-up belongs in the thread where the promise was made, on
    # the channel the customer used.
    if payload.status == "approved" and existing.get("action_type") in DRAFTABLE_ACTION_TYPES:
        conversation_id = existing.get("conversation_id") or ""
        pending_drafts = repository.list_reply_drafts(
            conversation_id=conversation_id, status="pending")
        if pending_drafts:
            raise HTTPException(
                status_code=409,
                detail="A pending reply draft already exists — send or discard it first.")
        draft = _build_follow_up_draft(repository, existing)

    # The other three nudges also answer with a message, and until now approving one did
    # nothing a customer could see. Kept as a SEPARATE branch rather than folded into
    # DRAFTABLE_ACTION_TYPES: that set also decides which cards carry a promise countdown
    # (_action_metadata), and adding these to it would hang a deadline clock on an empathy
    # nudge that has none.
    if (payload.status == "approved"
            and existing.get("action_type") in _ACK_OPENERS
            and draft is None):
        conversation_id = existing.get("conversation_id") or ""
        pending_drafts = repository.list_reply_drafts(
            conversation_id=conversation_id, status="pending")
        # Same one-draft-at-a-time rule the other two paths enforce. The composer holds one
        # pending draft per conversation, so a second would be unreachable.
        if pending_drafts:
            raise HTTPException(
                status_code=409,
                detail="A pending reply draft already exists - send or discard it first.")
        draft = _build_nudge_draft(repository, existing)

    # Approving a CLOSE PROPOSAL ends the case. This is the only place a customer-raised
    # proposal turns into a closed ticket, and it goes through the same POST /close path a
    # human uses from the ticket panel - so closed_by and closure_reason are written, the
    # CRM sync runs and the graph mirror updates. The customer's words propose; this line
    # is where a person decides.
    if payload.status == "approved" and existing.get("action_type") == ActionType.READY_TO_CLOSE.value:
        close_ticket_id = existing.get("ticket_id")
        if not close_ticket_id:
            raise HTTPException(status_code=400, detail="This proposal has no ticket to close.")
        current = repository.get_ticket(close_ticket_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if current.get("status") == "closed":
            raise HTTPException(status_code=409, detail="That case is already closed.")
        from services.ticket_service.ticket_manager import TicketManager
        TicketManager(repository, neo4j_client=_try_neo4j()).close(
            close_ticket_id,
            # The agent is closing on the strength of the customer's own words, so those
            # words ARE the reason. No model writes this sentence: the one thing a customer
            # wants recorded is why their case ended, and inventing that is the failure
            # this flow exists to prevent.
            existing.get("reason") or "Customer confirmed their case is resolved.",
            payload.actor,
        )

    updated = repository.update_agent_assist_recommendation(
        recommendation_id, status=payload.status, actor=payload.actor,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if draft is not None:
        updated = {**updated, "draft_id": draft.get("draft_id")}
    repository.add_audit_event(
        "nba_recommendation_" + payload.status,
        recommendation_id,
        customer_id=updated.get("customer_id"),
        conversation_id=updated.get("conversation_id"),
        ticket_id=updated.get("ticket_id"),
        details={"action_type": updated.get("action_type"), "actor": payload.actor},
    )
    return updated
