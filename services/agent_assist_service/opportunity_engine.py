"""Cross-sell / up-sell opportunity engine (LLM-selected, code-guarded).

Adapted from the nudge-engine reference (docs/CROSS_SELL_UPSELL_DESIGN.md) for
async ticket-based chat: no live transcript, so no listener/generator loop.
Division of labour, per that doc's hard-won lessons:

  - CODE owns the guardrails: when it is an acceptable moment to sell (gates),
    which products are even offerable (candidate set precomputed from the BFSI
    graph, "eligible-but-not-owned"), and validating that the LLM only picked
    from that set (never trust the LLM to obey the rules).
  - The LLM owns the judgment: which 1-2 candidates fit THIS customer's recent
    conversation, and a short pitch grounded in the customer's real numbers.

Output feeds the existing agent_assist_recommendations table; a human admin
approves/dismisses every item — nothing reaches a customer automatically.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from services.pii_service.masker import mask_text, unmask_text

logger = logging.getLogger(__name__)

MAX_OPPORTUNITIES = 2
_RECENT_TURNS_FOR_PROMPT = 10
_FD_MATURITY_WINDOW_DAYS = 90
# Balance comfortably above the account minimum → FD / premium-tier candidate.
_HIGH_BALANCE_MULTIPLE = 5

_LIFE_POLICY_TYPES = {"term insurance", "life", "life insurance"}
_HEALTH_POLICY_TYPES = {"health", "health insurance", "mediclaim"}
# Segment-vs-variant mismatch (rule 8): premium-tier customers on entry cards.
_ENTRY_CARD_VARIANTS = {"classic", "silver", "basic"}
_PREMIUM_SEGMENTS = {"hni", "premium", "wealth"}
# A seriously delinquent card (attrition scorer's strong-sign line) is the wrong
# premise for "you deserve a better card" — offer-targeting quality, not a gate.
_UPGRADE_MAX_DPD = 30
# Rule 9: repeated penalty charges → offer the tier that waives them.
_CHARGE_WAIVER_MIN_COUNT = 2
# Rule 10: recent-conversation intents mapped to the product family they express
# interest in. Only intents that RELIABLY imply a product family are listed —
# the taxonomy has no FD/insurance-purchase intent (those classify as
# general_inquiry), so this rule's coverage is loans/cards/policies by design.
_INTENT_PRODUCT_FAMILY = {
    "loan_status": "loan",
    "loan_application": "loan",
    "card_management": "credit_card",
    "policy_status": "policy",
}
_RECENT_INTENT_WINDOW = 10  # how many recent turns to scan for interest signals


# ── Gates: is this an acceptable moment to sell? ─────────────────────────────

def check_gates(*, tickets: list[dict], turns: list[dict]) -> str | None:
    """Return a suppression reason, or None when selling is acceptable.

    Single gate: don't pitch to a customer whose latest message is negative.
    Earlier drafts also gated on open tickets, card fraud/dpd, and High
    attrition; all dropped by user decision (2026-07-23) — the human admin
    reviewing each offer is the remaining judgment layer. `tickets` is kept
    in the signature for future re-tightening.
    """
    # Negative sentiment on the latest inbound message → wrong mood to pitch.
    for turn in reversed(turns):
        if turn.get("direction") != "inbound":
            continue
        sentiment = ((turn.get("metadata") or {}).get("sentiment") or "").lower()
        if sentiment == "negative":
            return "recent negative sentiment"
        break

    return None


# ── Candidate set: what COULD we offer? (reference doc §5) ───────────────────

def _days_until(value) -> int | None:
    if not value:
        return None
    try:
        date = datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    return (date - datetime.now(timezone.utc)).days


def build_candidates(
    graph_context: dict,
    segment: str | None = None,
    charges: list[dict] | None = None,
    turns: list[dict] | None = None,
) -> list[dict]:
    """Deterministic eligible-but-not-owned gaps + upgrade candidates.

    Each candidate: {product, kind, basis} — basis is the grounding fact the
    LLM must cite. The LLM may ONLY recommend products from this list.
    One candidate per product: if two rules fire for the same product, the
    first (appended) wins. `charges` = ChargePenalty rows (rule 9);
    `turns` = chronological conversation turns (rule 10).
    """
    loans = graph_context.get("loans") or []
    policies = graph_context.get("policies") or []
    cards = graph_context.get("credit_cards") or []
    accounts = graph_context.get("accounts") or []
    fds = graph_context.get("fixed_deposits") or []

    policy_types = {(p.get("policy_type") or "").strip().lower() for p in policies}
    candidates: list[dict] = []

    # Cross-sell: loan but no life/term cover (the pre-existing NBA rule).
    if loans and not (policy_types & _LIFE_POLICY_TYPES):
        amount = max((l.get("amount_inr") or 0) for l in loans)
        candidates.append({
            "product": "term_insurance", "kind": "cross_sell",
            "basis": f"holds a loan of INR {amount:,.0f} with no term/life cover on record",
        })

    # Cross-sell: no health policy at all.
    if not (policy_types & _HEALTH_POLICY_TYPES):
        candidates.append({
            "product": "health_insurance", "kind": "cross_sell",
            "basis": "no health insurance policy on record",
        })

    # Cross-sell: has an account but no credit card.
    if accounts and not cards:
        candidates.append({
            "product": "credit_card", "kind": "cross_sell",
            "basis": "active account holder with no credit card on record",
        })

    # Cross-sell / up-sell around balances.
    for acct in accounts:
        bal = acct.get("avg_monthly_balance")
        minbal = acct.get("min_balance_required")
        if bal is None or minbal is None or minbal <= 0:
            continue
        if bal >= minbal * _HIGH_BALANCE_MULTIPLE:
            if not fds:
                candidates.append({
                    "product": "fixed_deposit", "kind": "cross_sell",
                    "basis": f"avg monthly balance INR {bal:,.0f} vs INR {minbal:,.0f} minimum, no FD",
                })
            candidates.append({
                "product": "premium_account_tier", "kind": "up_sell",
                "basis": f"avg monthly balance INR {bal:,.0f} is {bal / minbal:.0f}x the account minimum",
            })
            break  # one balance-based grounding is enough

    # Up-sell: FD maturing soon → renewal/laddering.
    for fd in fds:
        days = _days_until(fd.get("maturity_date"))
        if days is not None and 0 <= days <= _FD_MATURITY_WINDOW_DAYS:
            principal = fd.get("principal_amount") or 0
            candidates.append({
                "product": "fd_renewal", "kind": "up_sell",
                "basis": f"FD of INR {principal:,.0f} matures in {days} days",
            })
            break

    # Up-sell: healthy card usage (reward points, not seriously overdue) → premium variant.
    for card in cards:
        points = card.get("reward_points_balance") or 0
        if points >= 5000 and (card.get("dpd") or 0) < _UPGRADE_MAX_DPD:
            variant = card.get("card_variant") or "current"
            candidates.append({
                "product": "premium_card_upgrade", "kind": "up_sell",
                "basis": f"{points:,} reward points on the {variant} card, payments on time",
            })
            break

    # Up-sell (rule 8): premium-segment customer on an entry-level card variant —
    # the bank already trusts them with a high limit but they hold the bottom-tier
    # product. Skipped when the card is seriously delinquent (dpd >= 30): wrong
    # premise for an upgrade offer.
    if (segment or "").strip().lower() in _PREMIUM_SEGMENTS:
        for card in cards:
            variant = (card.get("card_variant") or "").strip().lower()
            if variant in _ENTRY_CARD_VARIANTS and (card.get("dpd") or 0) < _UPGRADE_MAX_DPD:
                limit = card.get("credit_limit") or 0
                candidates.append({
                    "product": "premium_card_upgrade", "kind": "up_sell",
                    "basis": (f"{segment} customer on a {card.get('card_variant')} card "
                              f"with INR {limit:,.0f} limit — eligible for a premium variant"),
                })
                break

    # Rule 9 (cross/up-sell as saving): repeated non-reversed penalty charges →
    # offer the account tier that waives them. Sells by arithmetic — the pitch
    # is "stop paying these charges", the strongest customer-benefit story.
    unreversed = [
        ch for ch in (charges or [])
        if (ch.get("reversal_status") or "").strip().lower() not in ("reversed", "approved")
    ]
    if len(unreversed) >= _CHARGE_WAIVER_MIN_COUNT:
        total = sum(float(ch.get("amount") or 0) for ch in unreversed)
        kinds = {(ch.get("charge_type") or "charge").strip() for ch in unreversed}
        candidates.append({
            "product": "charge_waiver_account_upgrade", "kind": "up_sell",
            "basis": (f"{len(unreversed)} charges totalling INR {total:,.0f} "
                      f"({', '.join(sorted(kinds))}) — an upgraded account tier waives these"),
        })

    # Rule 10 (asked-about-product): the customer's recent messages carry an
    # intent for a product family they do NOT hold — the purest interest signal
    # there is. Coverage limited to intents that reliably imply a family (see
    # _INTENT_PRODUCT_FAMILY); FD/insurance questions classify as
    # general_inquiry in this taxonomy and cannot be mapped.
    held = {"loan": bool(loans), "credit_card": bool(cards), "policy": bool(policies)}
    recent = [t for t in (turns or []) if t.get("intent")][-_RECENT_INTENT_WINDOW:]
    for turn in reversed(recent):  # most recent interest first
        family = _INTENT_PRODUCT_FAMILY.get((turn.get("intent") or "").strip().lower())
        if not family or held.get(family, True):
            continue
        product = {"loan": "personal_loan_info", "credit_card": "credit_card",
                   "policy": "insurance_policy"}[family]
        when = str(turn.get("created_at") or "")[:10]
        candidates.append({
            "product": product, "kind": "cross_sell",
            "basis": (f"customer asked about {family.replace('_', ' ')}s in chat"
                      + (f" on {when}" if when else "") + f", holds none"),
        })
        break  # one interest-driven candidate is enough

    # One candidate per product (two rules can propose the same product).
    seen: set[str] = set()
    deduped = []
    for cand in candidates:
        if cand["product"] in seen:
            continue
        seen.add(cand["product"])
        deduped.append(cand)
    return deduped


# ── LLM prompt ───────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a BFSI cross-sell/up-sell assistant helping a human support agent.
You will be given a customer's profile, their product holdings, a list of ALLOWED
candidate offers, their recent support conversation, and offers already suggested.

Select AT MOST 2 candidates that best fit this customer RIGHT NOW and write a short
pitch for each. Rules:
1. You may ONLY pick products from the ALLOWED CANDIDATES list. Never invent an offer.
2. Prefer candidates connected to what the customer recently talked about.
3. Each pitch is ONE sentence, maximum 20 words, and MUST cite the customer's real
   numbers from the candidate's basis (amounts, days, points).
4. Never repeat or paraphrase an offer from the ALREADY SUGGESTED list.
5. If nothing fits well, return an empty array. Fewer good offers beat more weak ones.
6. Respond with ONLY a JSON array, no markdown, no commentary:
[{"product": "<product id from candidates>", "kind": "cross_sell|up_sell",
  "pitch": "<=20 word sentence>", "reason": "<why now, <=15 words>", "confidence": 0.0-1.0}]

GOOD pitch: "Your INR 5,00,000 FD matures in 40 days - renew now to lock today's rate."
GOOD pitch: "With INR 1,80,000 average balance, a fixed deposit could earn you far more."
BAD pitch (no numbers): "We have great fixed deposit options for valued customers like you."
BAD pitch (not in candidates): "Consider our new personal loan at attractive rates."
BAD pitch (too long): any sentence over 20 words."""


def build_user_prompt(
    *,
    customer: dict,
    graph_context: dict,
    candidates: list[dict],
    turns: list[dict],
    already_suggested: list[str],
) -> str:
    holdings = []
    for label, key in (("Loans", "loans"), ("Policies", "policies"), ("Credit cards", "credit_cards"),
                       ("Accounts", "accounts"), ("Fixed deposits", "fixed_deposits")):
        items = graph_context.get(key) or []
        if items:
            holdings.append(f"- {label}: {len(items)}")
    holdings_text = "\n".join(holdings) or "- none on record"

    cand_lines = "\n".join(
        f"- {c['product']} ({c['kind']}): {c['basis']}" for c in candidates
    )

    recent = [t for t in turns if t.get("text")][-_RECENT_TURNS_FOR_PROMPT:]
    convo_lines = "\n".join(
        f"{'Customer' if t.get('direction') == 'inbound' else 'Agent'}: {(t.get('text') or '')[:200]}"
        for t in recent
    ) or "(no recent messages)"

    suggested_text = "\n".join(f"- {s}" for s in already_suggested) or "- none"

    return f"""CUSTOMER PROFILE
- Name: {customer.get('name') or 'unknown'}
- Segment: {customer.get('segment') or 'unknown'}
- Holdings:
{holdings_text}

ALLOWED CANDIDATES (you may only pick from these)
{cand_lines}

RECENT CONVERSATION (oldest first)
{convo_lines}

ALREADY SUGGESTED (do not repeat these or similar)
{suggested_text}

Return the JSON array now."""


# ── LLM output post-processing (reference doc §4.4 / §6: never trust it) ─────

def _clean_json_array(text: str) -> str:
    start, end = text.find("["), text.rfind("]")
    return text[start:end + 1] if start != -1 and end >= start else text


def parse_and_validate(raw_text: str, candidates: list[dict]) -> list[dict]:
    """Parse the LLM's JSON and drop anything outside the candidate set.

    Returns [] on any parse failure (caller falls back to previously stored
    pending rows — the fail-safe rule: never blank the UI on an LLM error).
    """
    allowed = {c["product"]: c for c in candidates}
    try:
        parsed = json.loads(_clean_json_array(raw_text))
    except (json.JSONDecodeError, TypeError):
        logger.warning("opportunity_llm_output_unparseable: %.200s", raw_text)
        return []
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []

    results: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        product = str(item.get("product") or "").strip()
        candidate = allowed.get(product)
        if candidate is None:
            logger.info("opportunity_dropped_out_of_set product=%s", product)
            continue  # LLM invented an offer or picked an ineligible one
        pitch = str(item.get("pitch") or "").strip()
        if not pitch:
            continue
        if len(pitch.split()) > 25:  # small tolerance over the 20-word ask
            pitch = " ".join(pitch.split()[:25]) + "…"
        try:
            confidence = min(max(float(item.get("confidence") or 0.5), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.5
        results.append({
            "product": product,
            # kind comes from OUR candidate definition, not the LLM's claim.
            "kind": candidate["kind"],
            "pitch": pitch,
            "reason": str(item.get("reason") or "").strip()[:120],
            "basis": candidate["basis"],
            "confidence": confidence,
        })
        if len(results) >= MAX_OPPORTUNITIES:
            break
    return results


# ── Orchestration ────────────────────────────────────────────────────────────

def generate_opportunities(
    *,
    generator,
    customer: dict,
    graph_context: dict,
    tickets: list[dict],
    turns: list[dict],
    already_suggested: list[str],
    charges: list[dict] | None = None,
) -> dict:
    """Full pipeline: gates → candidates → LLM → validation.

    Returns {"suppressed": reason} when gated, {"opportunities": [...]} otherwise
    (possibly empty). `generator` is a GroqGenerator (duck-typed for tests).
    """
    reason = check_gates(tickets=tickets, turns=turns)
    if reason:
        return {"suppressed": reason}

    candidates = build_candidates(
        graph_context, segment=customer.get("segment"), charges=charges, turns=turns,
    )
    if not candidates:
        return {"opportunities": []}

    user_prompt = build_user_prompt(
        customer=customer,
        graph_context=graph_context,
        candidates=candidates,
        turns=turns,
        already_suggested=already_suggested,
    )
    # Mask PII before the prompt leaves the boundary, as every other prose call does
    # (answer_generation, intent_classification and case_summary all mask; handoff_check
    # masks at its own call site). This one did not, and it carries the widest customer
    # text of any of them: the customer's real name plus up to ten conversation turns,
    # verbatim. An account or card number the customer typed into a message went to the
    # provider unmasked - exactly what masker.py exists to catch.
    #
    # The whole assembled prompt is masked in one call rather than each input separately,
    # so a field added to build_user_prompt later cannot quietly escape masking. The
    # candidate block is masked too; candidate ids are code-generated product keys, so
    # there is nothing there for the patterns to match.
    # The customer's own identity values, so they are masked by exact match as well as by
    # pattern. Built inline rather than imported: groq_generator._known_values is private,
    # and every cross-service import of that module takes only the public GroqGenerator.
    known_values = {
        "name": graph_context.get("name") or "",
        "phone": graph_context.get("phone") or "",
        "email": graph_context.get("email") or "",
    } if graph_context else {}
    user_prompt, pii_mapping = mask_text(user_prompt, known_values)

    result = generator._generate(
        _SYSTEM_PROMPT,
        user_prompt,
        operation="opportunity_generation",
        metadata={"candidates": [c["product"] for c in candidates]},
    )
    if not result.get("llm_used"):
        return {"opportunities": [], "llm_error": result.get("error")}

    # Unmask before parsing: a pitch may address the customer by name, and the placeholder
    # must not reach the offer draft an agent approves and sends.
    raw_text = unmask_text(result.get("text") or "", pii_mapping)
    return {"opportunities": parse_and_validate(raw_text, candidates)}
