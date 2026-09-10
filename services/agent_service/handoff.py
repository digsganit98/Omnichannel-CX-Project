"""Does a human need to see this message? — decided by reading the message.

Every other escalation rule in `orchestration_agents._escalation_reason` keys off a
LABEL: an Intent enum value, a resolution level, a confidence score. That is how a real
complaint reached a customer unreviewed on 2026-09-02:

    "I've uploaded those documents already and nothing has happened.
     This is unacceptable. Please help me."

The intent classifier returned `claim_status` at 0.95 confidence, reasoning "customer
wants an update on an existing claim". `claim_status` is in INFORMATIONAL_INTENTS, so
Rule 3b returned None and the reply auto-sent — telling her to upload the documents she
had just said she already uploaded. Sentiment was correctly detected as `negative` and
read by nothing.

The defect is structural, not a missing keyword: a decision about whether a human must
see a message was being made without the message. One 16-way label carried it, with no
floor underneath. This module adds the missing input — the customer's own words — and
asks one question of them.

Deliberately NOT a third value on `l2_kind`. That field describes what kind of L2 a
query is, so it only speaks once the L2 gate is already open; a safety decision must not
sit behind another gate's preconditions.

Measured before it was built (14 cases x 3 runs, openai/gpt-oss-20b, temperature 0):
38/42, and every case returned the SAME answer on all three runs. The two messages that
prompted the work both decide correctly and stably — the complaint holds
(service_failure_asserted 3/3), the document question does not (3/3), and the controls
("can you help me check my balance?", "URGENT!! What are your FD rates??") do not.
"""
from __future__ import annotations

import json
import logging
import re

from services.pii_service.masker import mask_text

logger = logging.getLogger(__name__)


# Closed set. A free-text reason would be prose; these map 1:1 to hold labels in
# review_gate, so the queue can say WHY without a human re-reading the message.
HANDOFF_REASONS = {
    "human_requested",
    "service_failure_asserted",
    "emergency",
    "distress",
    "approval_needed",
}


# Deterministic floor, checked BEFORE the model. Mirrors the high-risk net in
# resolution_service.classifier, which already establishes the pattern and the principle:
# a small, unambiguous list where over-triggering is the safe direction. This is not the
# mechanism — the judgement below is — it is what still works when the model is wrong,
# slow, or the daily request budget is gone.
#
# Kept deliberately short. "help me" is NOT here and must never be: "can you help me
# check my balance?" is a request for information, and the probe confirms the model
# already answers it correctly without being told about the phrase.
_HUMAN_REQUEST_PATTERNS = [
    r"\b(speak|talk|chat)\s+(to|with)\s+(a\s+|an\s+|the\s+)?(human|person|agent|representative|advisor|someone)\b",
    r"\b(connect|transfer|put)\s+me\s+(to|with|through)\b",
    r"\bi\s+want\s+(to\s+speak\s+to\s+)?(a\s+|an\s+)?(human|person|agent|representative)\b",
    r"\b(real|actual|live)\s+(person|human|agent)\b",
    r"\bnot\s+(a\s+)?(bot|robot|machine|ai)\b",
    r"\bstop\s+(sending|giving)\s+me\s+(automated|auto)\b",
]
_HUMAN_REQUEST_REGEX = re.compile("|".join(_HUMAN_REQUEST_PATTERNS), flags=re.IGNORECASE)


_SYSTEM_PROMPT = """You decide ONE thing: must a human being look at this customer message before a reply is sent?

You are reading the customer's own words. Do not infer from a category label — read what they wrote and what they are asking for.

Return ONLY valid JSON, no markdown or prose:
{"handoff": true|false, "reason": "<one of the reasons below, or null>", "confidence": 0.0-1.0}

Reasons (use exactly one when handoff is true):
- "human_requested"          The customer is asking to reach a person, an agent, or a representative.
- "service_failure_asserted" The customer states that something they already did, or something they were promised, did not work: they already sent/uploaded/called/paid, they are asking again, nothing happened, a deadline passed.
- "emergency"                Something time-critical where delay causes real harm.
- "distress"                 The customer is in a state that an accurate answer alone will not settle: anger, fear, desperation about their situation.
- "approval_needed"          They want an outcome the system cannot produce on its own: a fee waived, a decision reversed, a claim honoured, an exception made.

Set handoff false when the customer is asking a question that an accurate answer completes, however politely or urgently it is phrased. Wanting information is not the same as needing a person.

confidence is your certainty in the handoff value."""


def _pattern_match(text: str) -> str | None:
    match = _HUMAN_REQUEST_REGEX.search(text or "")
    return match.group(0) if match else None


def needs_human(text: str, generator=None) -> tuple[str | None, dict]:
    """Return ``(reason, detail)`` — reason is a HANDOFF_REASONS value, or None.

    Never raises and never blocks a reply: any failure (no client, bad JSON, timeout,
    quota exhausted) returns ``None`` so the existing rules decide alone. The floor is
    checked first so it still holds a "let me speak to a human" when the model is
    unavailable — that is the case where failing open would be worst.
    """
    clean = (text or "").strip()
    if not clean:
        return None, {"source": "empty"}

    matched = _pattern_match(clean)
    if matched:
        logger.info("handoff_pattern_matched", extra={"matched_term": matched})
        return "human_requested", {"source": "pattern", "matched": matched}

    try:
        if generator is None:
            from services.rag_service.groq_generator import GroqGenerator
            generator = GroqGenerator()
        # Masked like every other outbound prompt: the decision needs the SHAPE of the
        # complaint, never the account number inside it.
        masked, _ = mask_text(clean)
        # _generate (not the raw client) so the call is recorded in llm_usage_events —
        # an unrecorded probe cost 58 requests on 2026-09-02 with no way to see it.
        # json_mode makes the provider return a JSON document rather than prose that
        # happens to contain one.
        #
        # NO max_tokens. The answer is three short fields, so a small cap looks obviously
        # right — and it silently broke this in production: gpt-oss-20b is a REASONING
        # model that bills reasoning tokens against the same budget, so max_tokens=120
        # returned HTTP 400 and needs_human fell through to "no_response" on every
        # message. The fail-open design meant no error surfaced; the hold just never
        # fired. Measured: 120 -> 400 error, 400 -> correct verdict, none -> correct.
        result = generator._generate(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=masked,
            operation="handoff_check",
            json_mode=True,
        )
    except Exception:
        logger.warning("handoff_check_failed", exc_info=True)
        return None, {"source": "error"}

    if not result or not result.get("llm_used"):
        return None, {"source": "no_response"}

    try:
        text = str(result.get("text") or "")
        payload = json.loads(text[text.find("{") : text.rfind("}") + 1])
    except (ValueError, TypeError):
        logger.warning("handoff_check_unparseable", extra={"raw": str(result)[:200]})
        return None, {"source": "unparseable"}

    if not payload.get("handoff"):
        return None, {"source": "llm", "handoff": False}

    reason = str(payload.get("reason") or "").strip().lower()
    if reason not in HANDOFF_REASONS:
        # Validated, not trusted. The probe saw the right DECISION with an off reason
        # twice (an emergency labelled service_failure_asserted); an unrecognised value
        # must still hold, because the boolean is the safety-bearing half.
        logger.info("handoff_reason_unrecognised", extra={"reason": reason})
        reason = "distress"

    return reason, {
        "source": "llm",
        "handoff": True,
        "confidence": payload.get("confidence"),
    }
