"""One LLM call that reviews ONE case for the agent who just opened it.

Replaces three calls that each re-sent the same case:

    case_summary            721 tok/call   "explain this case to someone cold"
    case_advice           1,221 tok/call   "what needs saying to this customer"
    opportunity_generation  879 tok/call   "what could we offer them"
                          ─────────────
                          2,821 tokens, three copies of the same conversation

MEASURED on the live fraud case (2026-09-13): 973 prompt + 1,107 completion = 2,080
total. A 26% saving, and it comes almost entirely from the prompt side - the case
context is assembled once instead of three times.

Do NOT restate the saving as "half the cost". It was claimed as half, then as ~1,200
tokens, before either was measured; both were wrong. 26% is the number that came off a
usage row.

SCOPED TO THE CASE, WHICH IS THE BIGGER CHANGE
----------------------------------------------
The three old calls were handed the whole CONVERSATION. On the live customer that is 30
turns spanning 8 different tickets - a fraud dispute, a claim query, loan questions - of
which 4 belong to the case on screen. The model was reasoning about a loan enquiry while
advising on a fraud dispute, and the summary needed a redaction hack because our own
quoted status emails let a since-resolved ticket id outnumber the authoritative block 4:1.

This takes one ticket's turns. Smaller AND more accurate, and the truncation the old
prompt needed (last 8 turns, 180 chars each) is gone: a single case fits whole.

DIVISION OF LABOUR - unchanged from the two engines this replaces
-----------------------------------------------------------------
  - CODE owns the guardrails: the gates, the vocabulary, the candidate set, PII masking,
    and validating that the model stayed inside all of them.
  - The LLM owns the judgement: given one case, what is going on and what needs saying.

THE GATES ARE OPPOSITES AND BOTH ARE DELIBERATE
------------------------------------------------
Offers are suppressed on negative sentiment - the wrong moment to sell. Actions are NOT -
an angry customer is exactly who we owe a follow-up. One call, but the offers section is
simply omitted from the request when the sentiment gate fires, so the decision stays in
code and the model is never asked to police it.

It does NOT write the customer-facing message. See case_advisor's module docstring: probed
against this same case, the model claimed we had blocked a card we had not and escalated a
case that did not exist. Nudges carry a reason; the agent writes the words.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from services.agent_assist_service import opportunity_engine
from services.agent_assist_service.case_advisor import ACTION_TYPES, _when
from services.pii_service.masker import mask_text, unmask_text
# The shared graph-context renderer. answer_generation and classify_message already use it;
# reusing it here is what stopped this prompt carrying counts where the others carry facts.
from services.rag_service.groq_generator import _format_graph_context

logger = logging.getLogger(__name__)

MAX_ACTIONS = 3
MAX_OFFERS = 2
_MAX_TURN_CHARS = 400

# MEASURED, not chosen. At 2,500 this call fails with a hard 400 "Failed to validate JSON"
# and an EMPTY failed_generation: gpt-oss bills reasoning tokens before emitting any of the
# answer, and json_mode rejects a truncated object outright rather than returning partial
# text. 4,000 succeeds. The same trap cost case_advisor a rebuild at 900 -> 2,000, and this
# response carries three sections instead of one.
MAX_TOKENS = 4000

_SYSTEM_PROMPT = (
    "You review ONE support case for the agent who has just opened it.\n"
    "\n"
    "Return ONLY a JSON object:\n"
    '{"situation":"...","actions":[{"type":"...","reason":"...","basis":"...","confidence":0.0}],'
    '"offers":[{"product":"...","kind":"...","pitch":"...","reason":"...","confidence":0.0}]}\n'
    "\n"
    "SITUATION - this case in 2-3 sentences, for someone picking it up cold.\n"
    "\n"
    "ACTIONS - reasons to WRITE to the customer. ONLY these four types:\n"
    "promised_update    = we said we would come back and have not. NOT general urgency.\n"
    "information_needed = blocked until THE CUSTOMER gives us something - a document, a\n"
    "                     confirmation, a choice. NOT anything the agent checks internally.\n"
    "                     If the last Agent turn ALREADY asked for it, keep this type but\n"
    "                     write `reason` as waiting, not as a fresh instruction:\n"
    "                     \"Asked for bills and medical reports - awaiting them\", NOT\n"
    "                     \"Customer must submit documents\".\n"
    "proactive_warning  = something in THEIR RECORDS will cost or affect them and they do\n"
    "                     not know yet. NOT a restatement of how they feel.\n"
    "acknowledgement    = they are upset and nobody has said so out loud.\n"
    "\n"
    "OFFERS - at most 2, ONLY products from ALLOWED CANDIDATES. Cite their real numbers.\n"
    "Never promise or imply an outcome: no approval, no guaranteed rate, no eligibility.\n"
    "Max 20 words per pitch. An empty array is correct when nothing fits.\n"
    "\n"
    "HARD RULES\n"
    "1. Do NOT write a message to the customer. You are briefing the agent.\n"
    "2. NEVER suggest an internal check, lookup, escalation or system fix. If the only next\n"
    "   step is something the agent does internally, return no action for it.\n"
    "3. State only what the CASE FACTS or CUSTOMER RECORDS support. Never assert that an\n"
    "   action was completed,\n"
    "   or that a deadline has passed, unless a fact says so explicitly.\n"
    "4. `confidence` is 0 to 1 and must MEAN something. Reserve above 0.9 for what the\n"
    "   record states outright; use 0.5-0.7 where you are inferring. Never 1.0 for all.\n"
    '5. `basis` must QUOTE the exact record you read it from, e.g. "Claim CLM001003, status\n'
    '   Under Review, awaiting supporting documents". NEVER a category name like "Case\n'
    '   facts" or "Sentiment analysis".\n'
    "6. Copy any date EXACTLY as written in CASE FACTS. Never invent a countdown like\n"
    '   "in 8 hours" - this text is stored and read later, when anything relative is wrong.\n'
    f"7. At most {MAX_ACTIONS} actions. Fewer is better. An empty list is a valid answer.\n"
)


def check_gates(*, ticket: dict | None, pending_drafts: list[dict]) -> str | None:
    """Return a suppression reason for the whole review, or None.

    Identical to case_advisor.check_gates - a held draft means the agent's next action is
    that draft, and a closed case has nothing outstanding. Deliberately says nothing about
    sentiment: that gates OFFERS only, below.
    """
    if pending_drafts:
        return "a reply is already held for review"
    if ticket and str(ticket.get("status") or "").lower() == "closed":
        return "the case is closed"
    return None


def offers_suppressed(sentiment: str | None) -> str | None:
    """Whether to leave offers out of this review.

    The opposite of the actions gate, and that is the point: an angry customer is the wrong
    person to sell to and exactly the right person to chase what we owe them. Mirrors
    opportunity_engine.check_gates, which reads the latest inbound turn's sentiment; here
    the already-aggregated label is used so the card and the right panel cannot disagree.
    """
    label = (sentiment or "").lower()
    if "frustrat" in label or "negative" in label:
        return "recent negative sentiment"
    return None


def build_user_prompt(*, ticket: dict | None, turns: list[dict], graph_context: dict,
                      sentiment: str | None, candidates: list[dict]) -> str:
    """Assemble ONE case. Every input here is already fetched for some panel on screen.

    `ticket` may be None: a conversation can have turns before any ticket exists, and that
    customer still needs acknowledging. The engine this replaces advised on those, so
    refusing them here would silently drop nudges the product used to make.
    """
    facts: list[str] = []
    if ticket:
        facts.append(
            f"- Case: {ticket.get('intent')} | priority {ticket.get('priority')} "
            f"| status {ticket.get('status')}"
        )
        facts.append(f"- Opened: {_when(ticket.get('created_at'))}")
        facts.append(
            f"- First answered: {_when(ticket['first_response_at'])}"
            if ticket.get("first_response_at") else "- NOT ANSWERED YET by a human"
        )
        if ticket.get("follow_up_due_at"):
            facts.append(
                f"- We promised an update, due {_when(ticket['follow_up_due_at'])}; "
                "nothing sent since we promised it"
            )
    else:
        facts.append("- No case has been opened for this conversation yet")

    # The SHARED renderer, the one answer_generation and classify_message already use. It
    # prints whatever the node carries, so a field added to the graph appears here with no
    # code change - and nothing can be silently omitted.
    #
    # This block used to be hand-written: segment, then a COUNT of each holding
    # ("Credit cards: 1"), then three claims and three transactions. Measured against the
    # same payload, that dropped DPD 45, the Rs.1,258 late-payment penalty, the Rs.1,284
    # LateFee charge and the Rs.91,821 due - every fact a proactive_warning is defined
    # against, so that action type could not fire on any case.
    #
    # _format_graph_context's own docstring records this exact bug being fixed once before:
    # "six hand-written blocks used to sit here, each naming the 4-6 fields it printed...
    # her charges were absent entirely". A seventh was written here anyway.
    records_text = _format_graph_context(graph_context)

    # THIS case's turns, whole. No 8-turn window and no 180-char truncation: those existed
    # because the old prompt carried a 30-turn conversation spanning every ticket.
    convo = "\n".join(
        f"{'Customer' if t.get('direction') == 'inbound' else 'Agent'}: "
        f"{(t.get('text') or '')[:_MAX_TURN_CHARS]}"
        for t in turns if t.get("text")
    ) or "(no messages on this case)"

    blocks = [
        "CASE FACTS\n" + "\n".join(facts),
        "THIS CASE'S CONVERSATION\n" + convo,
        "CUSTOMER RECORDS\n" + (records_text or "- none on record"),
        f"SENTIMENT: {sentiment or 'not assessed'}",
    ]
    if candidates:
        blocks.append(
            "ALLOWED CANDIDATES\n"
            + "\n".join(f"- {c['product']} | {c['kind']} | {c['basis']}" for c in candidates)
        )
    else:
        # Said explicitly rather than omitted: an absent block reads to the model as an
        # oversight, and rule 2 of the offers contract is that it may never invent one.
        blocks.append("ALLOWED CANDIDATES\n(none - return an empty offers array)")
    return "\n\n".join(blocks) + "\n"


def parse_and_validate(raw_text: str, candidates: list[dict]) -> dict | None:
    """Parse one response into three validated sections.

    Returns None on a parse failure so the caller can tell that apart from a case that
    genuinely needs nothing - rendering a failure as emptiness is what makes a broken
    check look like a clean case.
    """
    text = (raw_text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        logger.warning("case_review_output_unparseable: %.200s", raw_text)
        return None
    try:
        parsed = json.loads(text[start:end + 1])
    except (json.JSONDecodeError, TypeError):
        logger.warning("case_review_output_unparseable: %.200s", raw_text)
        return None
    if not isinstance(parsed, dict):
        return None

    situation = str(parsed.get("situation") or "").strip()

    actions: list[dict] = []
    for item in parsed.get("actions") or []:
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("type") or "").strip()
        if action_type not in ACTION_TYPES:
            # Dropped rather than coerced: a nudge whose type we guessed would drive the
            # wrong button on the card.
            logger.info("case_review_dropped_out_of_vocabulary type=%s", action_type)
            continue
        reason = str(item.get("reason") or "").strip()
        if not reason:
            continue
        try:
            confidence = min(max(float(item.get("confidence") or 0.5), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.5
        actions.append({
            "action_type": action_type,
            "reason": reason[:240],
            "basis": str(item.get("basis") or "").strip()[:160],
            "confidence": confidence,
        })
        if len(actions) >= MAX_ACTIONS:
            break

    # The offers validator is REUSED, not reimplemented: it is the rule that the model may
    # only name a product from our candidate set, and `kind` and `basis` come from OUR
    # definition rather than the model's claim. Two copies of that would drift.
    offers = opportunity_engine.parse_and_validate(
        json.dumps(parsed.get("offers") or []), candidates
    )[:MAX_OFFERS]

    return {"situation": situation, "actions": actions, "offers": offers}


def review(*, generator, ticket: dict | None, turns: list[dict], graph_context: dict,
           sentiment: str | None, pending_drafts: list[dict],
           charges: list[dict] | None = None, all_turns: list[dict] | None = None) -> dict:
    """Full pipeline: gates -> candidates -> prompt -> mask -> LLM -> unmask -> validate.

    Four outcomes, reported distinctly so three cards can each say which:

      {"suppressed": reason}     - deliberately silent, all three sections
      {"situation","actions","offers"}   - ran, any section may be empty
      {"llm_error": ...}         - FAILED. Never to be shown as "nothing to do".
      {"offers_suppressed": r}   - ran, but selling was gated off

    `all_turns` is the whole conversation and is used ONLY for the offer candidate rules,
    which look at what the customer has talked about across cases. The prompt itself sees
    this case's turns alone.
    """
    # A ticketless conversation is reviewed, not refused. check_gates already guards for it
    # (`if ticket and ...`), and the engine this replaces advised on exactly these: a
    # customer two angry messages in, before anything has been ticketed, is precisely who
    # an acknowledgement nudge is for.
    reason = check_gates(ticket=ticket, pending_drafts=pending_drafts)
    if reason:
        return {"suppressed": reason, "situation": "", "actions": [], "offers": []}

    offers_gate = offers_suppressed(sentiment)
    candidates: list[dict] = []
    if not offers_gate:
        # charges and turns are REQUIRED arguments in practice: without them this returns
        # [] on a customer who genuinely has a candidate, which is how the first two probe
        # runs tested the offers section against an empty list and proved nothing.
        candidates = opportunity_engine.build_candidates(
            graph_context,
            segment=graph_context.get("segment"),
            charges=charges if charges is not None else graph_context.get("charges"),
            turns=all_turns if all_turns is not None else turns,
        )

    user_prompt = build_user_prompt(
        ticket=ticket, turns=turns, graph_context=graph_context,
        sentiment=sentiment, candidates=candidates,
    )
    # Mask the WHOLE assembled prompt in one call, as both engines this replaces do, so a
    # field added to build_user_prompt later cannot quietly escape masking. The customer's
    # own identity values go in by exact match as well as by pattern.
    known_values = {
        "name": graph_context.get("name") or "",
        "phone": graph_context.get("phone") or "",
        "email": graph_context.get("email") or "",
    } if graph_context else {}
    user_prompt, pii_mapping = mask_text(user_prompt, known_values)

    result = generator._generate(
        _SYSTEM_PROMPT,
        user_prompt,
        operation="case_review",
        json_mode=True,
        max_tokens=MAX_TOKENS,
    )
    if not result.get("llm_used"):
        return {"llm_error": result.get("error") or "llm unavailable",
                "situation": "", "actions": [], "offers": []}

    raw_text = unmask_text(result.get("text") or "", pii_mapping)
    parsed = parse_and_validate(raw_text, candidates)
    if parsed is None:
        # Parsed to nothing from a non-empty response: the model answered in a shape we do
        # not accept. That is a failure, not an empty case, and must not retire live rows.
        return {"llm_error": "unparseable response", "situation": "", "actions": [], "offers": []}

    parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
    if offers_gate:
        parsed["offers_suppressed"] = offers_gate
    return parsed
