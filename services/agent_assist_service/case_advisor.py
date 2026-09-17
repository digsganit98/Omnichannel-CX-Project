"""What should the agent do next on this case — decided by the LLM, guarded by code.

Replaces the four hardcoded `if` rules in next_best_action.py. Those rules only ever fired
on the situations somebody had anticipated in advance: an aging SLA, a run of negative
messages, a stalled KYC. A rule cannot notice that a frustrated customer mid-fraud-dispute
also has a rejected claim and 45 days past due, because nobody wrote that combination down.

Division of labour, the same one opportunity_engine.py records:

  - CODE owns the guardrails: when it is acceptable to suggest anything (gates), which
    action types exist at all (vocabulary), PII masking, and validating that the model
    only used the vocabulary. Never trust the model to obey the rules.
  - The LLM owns the judgement: given the whole case, what needs saying and why.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not write the customer-facing message. That was the original design and it was
abandoned after probing it against this live fraud case (2026-09-13). Given the real
record, the model wrote:

    "I've escalated your fraud report ... and have blocked your debit card immediately"

Neither had happened: the earlier reply told the CUSTOMER to block the card, and the CRM
sync had failed so no case existed to escalate. Adding hard anti-fabrication rules to the
prompt stopped the invention but produced hollow text instead, with the agent-facing
placeholders leaking into the customer-facing message.

The cause is structural, not a prompt problem: the only thing the customer actually wants
is the investigation outcome, and NOTHING IN THIS SYSTEM KNOWS IT. A model asked to write
that sentence can only invent it or leave a hole.

So the nudge carries a REASON, and approving it opens a short skeleton draft the agent
completes. The knowledge lives with the human; the recall and the noticing live here.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from services.pii_service.masker import mask_text, unmask_text

logger = logging.getLogger(__name__)


# Everything is STORED in UTC (repository.utc_now) and read by people in India. _when
# formatted the UTC clock directly, so a follow-up due 11:08am IST was shown to the agent
# as "5:38am" - five and a half hours early, on the one sentence that tells them when they
# promised to reply. The browser-side formatters were always right: they use toLocale*,
# which renders in the viewer's zone. This text cannot, because it is generated on the
# server and STORED on the recommendation row, so the zone is pinned here instead.
# Same conversion the hourly analytics rollup already applies in SQL
# (repository.py: strftime(..., '+5 hours', '+30 minutes')).
IST = timezone(timedelta(hours=5, minutes=30))


def _when(value) -> str:
    """A stored UTC timestamp as an IST time a person can read: "13 Sep, 10:21pm".

    ABSOLUTE, never relative. The model's sentence is written once and then stored on the
    recommendation row, so anything relative rots the moment it is read later - "due in 8
    hours" is wrong tomorrow, and so is "by 10:21pm today". The live countdown belongs in
    the UI, which recomputes it on every render from follow_up_due_at (see renderNbaActions
    in app.js), exactly as the Service Desk board already does.

    Before this, the raw DB value went into the prompt and the model faithfully copied it
    back: "We promised an update by 2026-09-13T22:21:27.137919Z", shown to a human.
    """
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return str(value)
    # A naive value is a UTC one: everything written here comes from utc_now(). Without
    # this, astimezone() would read it as the SERVER's local zone and shift it twice.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(IST)
    hour = parsed.hour % 12 or 12
    meridiem = "am" if parsed.hour < 12 else "pm"
    return f"{parsed.day} {parsed:%b}, {hour}:{parsed:%M}{meridiem}"

MAX_ACTIONS = 3
_RECENT_TURNS_FOR_PROMPT = 8
_MAX_TURN_CHARS = 180

# The vocabulary. Every entry is a REASON TO WRITE TO THE CUSTOMER - which is what this
# card is for. Internal chores are deliberately absent: "chase the CRM sync" is a
# connector fault that belongs with the other connector health in System Configuration,
# and "escalate to senior" is a routing decision, not something you say to anyone.
ACTION_TYPES = {
    # We committed to coming back to them and have not.
    "promised_update",
    # We cannot proceed until they give us something.
    "information_needed",
    # Something in their records will hurt them and they do not know yet.
    "proactive_warning",
    # They are upset and nobody has said so out loud.
    "acknowledgement",
}

# Each type is defined by what it IS and what it IS NOT. The negatives are not padding:
# probed against the live fraud case (2026-09-13) with one-line type names only, the model
# used `information_needed` for "the agent should confirm whether the card was blocked" -
# an internal check, the exact category this card excludes - and `proactive_warning` to
# restate that the customer was frustrated, while ignoring the genuine warning sitting in
# the records (a claim of INR 224,755 held up awaiting supporting documents). Adding the
# NOT clauses moved all three onto real, customer-facing ground.
_SYSTEM_PROMPT = (
    "You advise a bank support agent on which customers need to be WRITTEN TO, and why.\n"
    "\n"
    "Return ONLY a JSON object:\n"
    '{"actions":[{"type":"...","reason":"...","basis":"...","confidence":0.0}]}\n'
    "\n"
    "THE FOUR TYPES - each is a reason to send the CUSTOMER a message.\n"
    "promised_update    = we told them we would come back to them and have not.\n"
    "                     NOT for general urgency or priority.\n"
    "information_needed = we are blocked until THE CUSTOMER gives us something - a\n"
    "                     document, a confirmation, a choice. NOT for anything the agent\n"
    "                     has to look up, check or fix internally.\n"
    "proactive_warning  = something in THEIR RECORDS will cost or affect them and they do\n"
    "                     not know yet - a claim awaiting documents, a charge, an overdue\n"
    "                     amount. NOT a restatement of how they feel.\n"
    "acknowledgement    = they are upset and nobody has said so out loud.\n"
    "\n"
    "FIELDS\n"
    "`reason` - one sentence to the AGENT. Name the specific facts: amounts, ids, dates.\n"
    "  Copy any date EXACTLY as written below (e.g. \"13 Sep, 10:21pm\"). Never invent a\n"
    "  countdown like \"in 8 hours\" or \"today\" - this sentence is stored and read later,\n"
    "  when anything relative would be wrong.\n"
    "`basis`  - quote the exact record you read it from (e.g. \"Claim CLM001003, status\n"
    "  Under Review, awaiting supporting documents\"). Not a category name like \"Sentiment\".\n"
    "`confidence` - 0 to 1, and MEAN it. Reserve above 0.9 for something the record states\n"
    "  outright; use 0.5-0.7 where you are inferring. Do not return 1.0 for everything.\n"
    "\n"
    "HARD RULES\n"
    "1. Do NOT write a message to the customer. You are briefing the agent, not drafting.\n"
    "2. NEVER suggest an internal check, lookup, escalation or system fix. If the only next\n"
    "   step is something the agent does internally, return no action for it.\n"
    "3. State only what the CASE FACTS support. Never assert that an action has been\n"
    "   completed, or that a deadline has passed, unless a fact says so explicitly.\n"
    "4. Say nothing about outcomes marked NOT KNOWN. Those are for the agent to supply.\n"
    f"5. At most {MAX_ACTIONS} actions. Fewer is better. An empty list is a valid answer\n"
    "   when the case genuinely needs nothing.\n"
)


def check_gates(*, ticket: dict | None, pending_drafts: list[dict]) -> str | None:
    """Return a suppression reason, or None when suggesting is acceptable.

    Deliberately the OPPOSITE of the offers gate on sentiment. An angry customer is the
    wrong moment to sell and exactly the right moment to chase what we owe them, so
    negative sentiment does not appear here at all.
    """
    if pending_drafts:
        # A held reply is already waiting for this conversation. The agent's next action is
        # that draft; a second suggestion beside it competes with the thing it is telling
        # them to do.
        return "a reply is already held for review"
    if ticket and str(ticket.get("status") or "").lower() == "closed":
        return "the case is closed"
    return None


def build_user_prompt(*, ticket: dict | None, turns: list[dict], graph_context: dict,
                      promise: dict, sentiment: str | None) -> str:
    """Assemble the case. Everything here already exists and is already fetched for other
    panels - the conversation for the centre pane, the ticket for the board, the graph
    records for Customer Context. No new query; what is new is putting them in one place.
    """
    recent = [t for t in turns if t.get("text")][-_RECENT_TURNS_FOR_PROMPT:]
    convo_lines = "\n".join(
        f"{'Customer' if t.get('direction') == 'inbound' else 'Agent'}: "
        f"{(t.get('text') or '')[:_MAX_TURN_CHARS]}"
        for t in recent
    ) or "(no recent messages)"

    facts: list[str] = []
    if ticket:
        facts.append(f"- Case: {ticket.get('intent')} | priority {ticket.get('priority')} "
                     f"| status {ticket.get('status')}")
        if ticket.get("created_at"):
            facts.append(f"- Opened: {_when(ticket['created_at'])}")
        if ticket.get("first_response_at"):
            facts.append(f"- First answered: {_when(ticket['first_response_at'])}")
        else:
            facts.append("- NOT ANSWERED YET by a human")
        if ticket.get("crm_sync_status") == "failed":
            facts.append("- CRM sync FAILED: no case exists in the external system")
        if ticket.get("approval_status") == "pending":
            facts.append("- Approval PENDING: not yet signed off")
    if promise.get("due_at"):
        state = "OVERDUE" if promise.get("overdue") else "outstanding"
        facts.append(f"- We promised an update, {state}, due {_when(promise['due_at'])}; "
                     f"nothing sent since we promised it")

    # KEY NAMES ARE MEASURED, NOT GUESSED. get_customer_context_by_id returns exactly:
    # accounts, charges, city, claims, credit_cards, customer_id, email, fixed_deposits,
    # kyc, loans, name, open_cases, phone, policies, segment, transactions.
    # An earlier draft of this function read "pending_transactions" and "rejected_claims" -
    # neither exists, so the records block rendered "none on record" while the Customer
    # Context panel beside it showed a pending transaction of INR 29,419 and a rejected
    # claim of INR 96,400. The model would have been briefed blind on the two facts that
    # make this case worth writing about, with nothing to indicate anything was missing.
    records: list[str] = []
    if graph_context.get("segment"):
        records.append(f"- Segment: {graph_context['segment']}")
    for label, key in (("Accounts", "accounts"), ("Credit cards", "credit_cards"),
                       ("Loans", "loans"), ("Policies", "policies"),
                       ("Fixed deposits", "fixed_deposits")):
        items = graph_context.get(key) or []
        if items:
            records.append(f"- {label}: {len(items)}")

    # The detail that matters is inside these three, not their count: an amount and a
    # status is what makes a nudge specific enough for an agent to act on.
    # FIELD names are measured too, from the real node shapes. A claim has no "amount" -
    # it carries amount_claimed_inr / amount_approved_inr - and a charge's state lives in
    # reversal_status, not status. Guessing these renders a line with the status and no
    # money in it, which is the half that makes a nudge worth acting on.
    for key, label, fields in (
        ("transactions", "Transaction",
         ("txn_id", "amount", "txn_type", "status", "txn_date")),
        ("claims", "Claim",
         ("claim_id", "amount_claimed_inr", "status", "reason")),
        ("charges", "Charge",
         ("charge_type", "amount", "reversal_status", "reason")),
    ):
        for item in (graph_context.get(key) or [])[:4]:
            if not isinstance(item, dict):
                continue
            parts = [f"{f}={item[f]}" for f in fields
                     if item.get(f) not in (None, "", "N/A")]
            if parts:
                records.append(f"- {label}: {', '.join(parts)}")

    for case in (graph_context.get("open_cases") or [])[:3]:
        if isinstance(case, dict) and case.get("status"):
            records.append(f"- Other open case: {case.get('intent') or 'case'} "
                           f"({case['status']})")

    return f"""CASE FACTS (the only things known to be true)
{chr(10).join(facts) or '- no ticket on this conversation'}

NOT KNOWN - never assert these
- whether any investigation has started or finished
- whether any refund, reversal or block has been actioned
- anything the records below do not state

CUSTOMER RECORDS
{chr(10).join(records) or '- none on record'}

SENTIMENT: {sentiment or 'unknown'}

RECENT CONVERSATION (oldest first)
{convo_lines}

Return the JSON now."""


def parse_and_validate(raw_text: str) -> list[dict]:
    """Parse the model's JSON and drop anything outside the vocabulary.

    Returns [] on any parse failure. The CALLER must distinguish that from a genuine empty
    answer - see advise(), which reports llm_error separately so the UI can say "couldn't
    check" instead of "nothing to do". A failure rendered as emptiness is the trap recorded
    in ec2-operations.md, where a 429 cached as "no offers" and Refresh could not clear it.
    """
    text = (raw_text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end >= start:
        text = text[start:end + 1]
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        logger.warning("case_advisor_output_unparseable: %.200s", raw_text)
        return []

    items = parsed.get("actions") if isinstance(parsed, dict) else parsed
    if not isinstance(items, list):
        return []

    results: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("type") or "").strip()
        if action_type not in ACTION_TYPES:
            # The model invented a type. Dropped rather than coerced: a nudge whose type we
            # guessed would drive the wrong button on the card.
            logger.info("case_advisor_dropped_out_of_vocabulary type=%s", action_type)
            continue
        reason = str(item.get("reason") or "").strip()
        if not reason:
            continue
        try:
            confidence = min(max(float(item.get("confidence") or 0.5), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.5
        results.append({
            "action_type": action_type,
            "reason": reason[:240],
            "basis": str(item.get("basis") or "").strip()[:160],
            "confidence": confidence,
        })
        if len(results) >= MAX_ACTIONS:
            break
    return results


def advise(*, generator, ticket: dict | None, turns: list[dict], graph_context: dict,
           promise: dict, sentiment: str | None, pending_drafts: list[dict]) -> dict:
    """Full pipeline: gates -> prompt -> mask -> LLM -> unmask -> validate.

    Three outcomes, reported distinctly so the UI can too:
      {"suppressed": reason}        - deliberately silent
      {"actions": [...]}            - ran, possibly empty
      {"actions": [], "llm_error":} - FAILED. Never to be shown as "nothing to do".
    """
    reason = check_gates(ticket=ticket, pending_drafts=pending_drafts)
    if reason:
        return {"suppressed": reason, "actions": []}

    user_prompt = build_user_prompt(
        ticket=ticket, turns=turns, graph_context=graph_context,
        promise=promise, sentiment=sentiment,
    )
    # Mask the WHOLE assembled prompt in one call, as the offers engine does, so a field
    # added to build_user_prompt later cannot quietly escape masking. The customer's own
    # identity values go in by exact match as well as by pattern.
    known_values = {
        "name": graph_context.get("name") or "",
        "phone": graph_context.get("phone") or "",
        "email": graph_context.get("email") or "",
    } if graph_context else {}
    user_prompt, pii_mapping = mask_text(user_prompt, known_values)

    # 2000, not 900. MEASURED against this prompt on gpt-oss-20b: at 900 the call fails
    # with a 400 "Failed to validate JSON" and an EMPTY failed_generation; at 2000 and 3000
    # it succeeds identically. The model bills reasoning tokens before it emits any of the
    # answer, so a ceiling that fits the visible JSON does not fit the call - and because
    # json_mode rejects a truncated object outright rather than returning partial text, the
    # symptom is a hard error rather than a short answer. 3000 bought nothing over 2000.
    result = generator._generate(
        _SYSTEM_PROMPT,
        user_prompt,
        operation="case_advice",
        json_mode=True,
        max_tokens=2000,
    )
    if not result.get("llm_used"):
        return {"actions": [], "llm_error": result.get("error") or "llm unavailable"}

    raw_text = unmask_text(result.get("text") or "", pii_mapping)
    actions = parse_and_validate(raw_text)
    if not actions and (result.get("text") or "").strip():
        # Parsed to nothing from a non-empty response: the model answered in a shape we do
        # not accept. That is a failure, not an empty case, and must not silently retire
        # live rows downstream.
        logger.warning("case_advisor_empty_after_validation conv_turns=%d", len(turns))
    return {"actions": actions}
