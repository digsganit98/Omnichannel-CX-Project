"""Which of a customer's record fields should the model see for THIS question?

Replaces a hand-written column list per record type. Those lists were precise for the
questions whoever wrote them anticipated, and blind to everything else:

    "How many EMIs have I paid so far, and how many remain?"

was answered "the system does not have the detailed EMI payment schedule" while the Loan
node held emis_paid=53, emis_pending=1, total_emis=54. The three fields were simply not in
`get_loan_status`'s RETURN clause. The same shape of gap made every ChargePenalty
unreachable: no intent routed to charges, so a Rs.1,284 late fee could not be explained at
all.

Two tiers decide what is sent, and only the second depends on the question:

  1. ALWAYS - anything the customer would want raised whether they asked or not: a rejected
     claim, a failed transfer, an overdue loan, a non-zero penalty. Ranking cannot find
     these, because the words never appear in the question. Fathima asked about EMI counts;
     she also needs to know she is 15 days overdue with a penalty applied.
  2. RANKED - the top N fields by relevance to the question.

The ranking text is the question PLUS the intent. Intent is a signal here, not a gate: it
no longer decides which records exist or whether the customer gets data at all, so a
misclassification costs some ranking accuracy instead of routing to the wrong table. It
earns its place - measured on "what is my minimum amount due?", which contains no word
linking it to a card: without the intent, card_id/card_network/card_variant all fall out of
the top 10 and the reply cannot say WHICH card. With it, they rank in.

Measured across 9 questions on 7 node types (2026-09-04): zero fields lost against what the
hardcoded queries send today, and zero needed fields missing.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

DEFAULT_TOP_N = 15

# Never sent, whatever the question. Identifiers the masker would replace anyway, and
# internal machinery that is not an answer to anything.
_EXCLUDED_FIELDS = {
    "account_number", "card_number", "embedding", "record_hash",
    "created_at", "updated_at",
}

# Values that mean something is wrong or unfinished. Derived by reading every distinct
# status-like value in the graph, NOT invented - an earlier hand-written list both missed
# `kyc_status` (its name did not match) and wrongly treated `Matured` and `Under Review` as
# problems. Matching on the VALUE rather than the field name is what closes that gap: a
# Pending KYC is caught because the value is Pending, whatever the field is called.
#
# This list reflects the values present today. A state that has never appeared - Frozen,
# Lapsed, Blocked - would not be caught, so it needs revisiting when the data gains one.
_ABNORMAL_VALUES = {
    "rejected", "failed", "pending", "debited-pending-credit",
    "disputed", "overdue", "declined", "bounced", "expired",
}

# Numeric fields where any non-zero value is worth surfacing on its own.
_PROBLEM_FIELD_RE = re.compile(r"dpd|penalty|arrear|overdue|bounce", re.IGNORECASE)
_ZEROISH = {"0", "0.0", "false", "no", "none", "null", ""}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _humanise(field: str) -> str:
    return field.replace("_", " ")


def _is_abnormal(field: str, value) -> bool:
    """True when this value is worth telling the customer about unprompted."""
    text = str(value).strip().lower()
    if text in _ZEROISH:
        return False
    if any(flag in text for flag in _ABNORMAL_VALUES):
        return True
    if _PROBLEM_FIELD_RE.search(field):
        return text not in _ZEROISH
    return False


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def select_fields(
    question: str,
    properties: dict,
    intent: str | None = None,
    top_n: int = DEFAULT_TOP_N,
    embedder=None,
) -> dict:
    """Return the subset of ``properties`` this question should be answered from.

    Order is preserved as: abnormal-state fields first (they are the ones a customer needs
    raised whether or not they asked), then the ranked remainder.

    Never raises. If the embedding model is unavailable the word-overlap half still ranks,
    and if that fails too the first ``top_n`` fields are returned - degraded, but never
    empty, because an empty record set is the failure this module exists to remove.
    """
    if not properties:
        return {}

    usable = {k: v for k, v in properties.items()
              if k not in _EXCLUDED_FIELDS and v not in (None, "")}
    if len(usable) <= top_n:
        return usable  # nothing to choose between; send the record whole

    forced = {k: v for k, v in usable.items() if _is_abnormal(k, v)}
    remaining = {k: v for k, v in usable.items() if k not in forced}
    slots = max(0, top_n - len(forced))
    if slots == 0:
        return forced

    # The intent joins the question as ranking TEXT, not as a filter. See module docstring.
    query_text = f"{question} {_humanise(intent or '')}".strip()
    query_words = _words(query_text)

    query_vector = None
    if embedder is not None:
        try:
            query_vector = embedder.embed_query(query_text)
        except Exception:
            logger.warning("field_ranker_embedding_failed", exc_info=True)

    scored: list[tuple[float, str]] = []
    for field in remaining:
        label = _humanise(field)
        label_words = _words(label)
        overlap = len(query_words & label_words) / max(1, len(label_words))
        similarity = 0.0
        if query_vector is not None:
            try:
                similarity = _cosine(query_vector, embedder.embed_query(label))
            except Exception:
                similarity = 0.0
        scored.append((0.5 * overlap + 0.5 * similarity, field))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    ranked = {field: remaining[field] for _, field in scored[:slots]}
    return {**forced, **ranked}
