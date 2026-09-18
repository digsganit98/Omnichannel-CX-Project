"""What this workspace is configured to run, for the System Configuration page.

READ-ONLY, and deliberately so. Nothing here writes: the runtime is fixed when a container
is CREATED, so a value changed from a browser would not take effect until the service was
recreated - a form that appeared to work and did not is worse than no form.

ASSEMBLED, NOT RE-DERIVED. The live probes already exist and each one performs a REAL check
rather than reporting what is configured:

    GroqGenerator().status(check_connection=True)  -> models.list(), so `reachable` is a
                                                      round trip, not a key presence test
    /admin/rag/health                              -> loads the embedding model, so
                                                      `active_backend` can DISAGREE with
                                                      the requested one
    /admin/neo4j/status                            -> a Cypher count per label

Reading them here rather than reimplementing is what stops this page disagreeing with the
panels that already show the same facts - the failure recorded in the analytics rollup,
where an SLA count computed twice read 2 in one place and 7 in another.

SECRETS ARE NEVER RETURNED. Every credential is reduced to a boolean before it leaves this
module. A configuration page that prints a token is a configuration page that leaks one
into a screenshot.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends

from apps.api.dependencies.security import require_admin_auth
from services.rag_service.config import (
    embedding_backend,
    embedding_dimension,
    embedding_model,
    rag_backend,
    rag_top_k,
)
from services.agent_assist_service.case_reviewer import MAX_TOKENS as CASE_REVIEW_MAX_TOKENS
from services.rag_service.groq_generator import (
    CUSTOMER_CONTEXT_MAX_TOKENS,
    REASONING_EFFORT_OPERATIONS,
    TEMPERATURE,
    GroqGenerator,
    _reasoning_effort,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/system", tags=["admin"],
                   dependencies=[Depends(require_admin_auth)])


def _is_set(name: str) -> bool:
    """Whether a credential is present. Never its value."""
    return bool((os.getenv(name) or "").strip())


# Every LLM operation, with the settings it actually runs under. This table is the
# substance of the Model section: the operations do NOT share a configuration, and until
# now that was only visible by reading four files.
#
# The ceilings are IMPORTED from the modules that enforce them, never retyped: this table
# used to carry 4000 as a literal beside case_review, so tuning MAX_TOKENS in case_reviewer
# would have left the page confidently reporting the old number. Only `fires` and `note` are
# editorial, because no constant can express them.
#
# `max_tokens` is MEASURED, not chosen. case_review at 2,500 fails with a hard 400
# (json_validate_failed) and an EMPTY failed_generation, because a reasoning model bills
# the tokens it spends thinking BEFORE it emits any of the answer, and json_mode rejects a
# truncated object outright rather than returning a partial string.
#
# case_advice is NOT listed. It has no production caller (case_review replaced it) and has
# never fired once - 0 rows in llm_usage_events. An operation that cannot run is not part of
# this system's configuration, and saying "kept on disk for its tests" put an internal
# detail about our repository on a page an operator reads.
#
# `reasoning_effort` applies to TWO operations, not globally - REASONING_EFFORT_OPERATIONS
# is the authority and is read at runtime below rather than copied, so this table cannot
# drift from the code that enforces it.
_OPERATIONS = [
    {"operation": "intent_classification", "surface": "customer message",
     "max_tokens": None, "json_mode": False, "fires": "every inbound message",
     "note": "the label it returns decides retrieval and the answer's content"},
    {"operation": "resolution_level_classification", "surface": "customer message",
     "max_tokens": None, "json_mode": False, "fires": "every inbound message",
     "note": "L1 / L2 / L3, which decides whether a human is held"},
    {"operation": "handoff_check", "surface": "customer message",
     "max_tokens": None, "json_mode": True, "fires": "every inbound message",
     "note": "deliberately uncapped - a ceiling of 120 returned 400 and the hold "
             "silently never fired, because the design fails open"},
    {"operation": "answer_generation", "surface": "customer message",
     "max_tokens": None, "json_mode": False, "fires": "every inbound message",
     "note": "the reply the customer reads"},
    {"operation": "ticket_referee", "surface": "customer message",
     "max_tokens": None, "json_mode": False, "fires": "when a case is already open",
     "note": "decides whether this message belongs to that case or opens a new one"},
    {"operation": "ticket_action_detection", "surface": "customer message",
     "max_tokens": None, "json_mode": False, "fires": "on an apparent close request",
     "note": "proposes a close; a human performs it"},
    {"operation": "case_review", "surface": "agent console",
     "max_tokens": CASE_REVIEW_MAX_TOKENS, "json_mode": True,
     "fires": "when an agent opens a case",
     "note": "one call behind all three case cards; 2,500 fails with a hard 400 because "
             "reasoning tokens are billed before any answer is emitted"},
    {"operation": "customer_context", "surface": "agent console",
     "max_tokens": CUSTOMER_CONTEXT_MAX_TOKENS, "json_mode": True,
     "fires": "on a context panel refresh",
     "note": "the heaviest operation on record and the only one that ever returned "
             "nothing; 8192 exceeded the per-minute ceiling on its own"},
]


@router.get("/config")
def system_config() -> dict:
    """Everything the System Configuration page shows, in one call.

    One request rather than six, because the page renders as a whole: six independent
    fetches would paint the sections at six different times and any one of them failing
    would leave a section saying "Loading..." for ever.
    """
    llm = GroqGenerator()
    try:
        llm_status = llm.status(check_connection=True)
    except Exception as exc:  # a probe must never 500 the page
        logger.warning("system_config_llm_probe_failed: %s", exc)
        llm_status = {"provider": "groq", "model": llm.model, "reachable": None,
                      "error": str(exc)}

    effort = _reasoning_effort()
    # Provider, model and temperature are stamped PER OPERATION, not reported once for the
    # page. Today every operation resolves to the same provider and model - but that is a
    # fact about this configuration, not about the system: nothing stops a cheap classifier
    # and the customer-facing reply being routed to different models, and a single "the
    # model" heading would become wrong the moment they were. The table is the shape that
    # survives that change; a summary card is not.
    operations = [
        dict(op,
             provider=llm_status.get("provider"),
             model=llm_status.get("model"),
             temperature=TEMPERATURE,
             reasoning_effort=effort if op["operation"] in REASONING_EFFORT_OPERATIONS
             else None)
        for op in _OPERATIONS
    ]

    return {
        "model": {
            "provider": llm_status.get("provider"),
            "model": llm_status.get("model"),
            "reachable": llm_status.get("reachable"),
            "error": llm_status.get("error"),
            "credential_set": llm_status.get("api_key_configured"),
            "timeout_seconds": llm_status.get("timeout_seconds"),
            "available_models": llm_status.get("available_models") or [],
            # Hardcoded in _generate's call_params, not an environment variable - so it is
            # reported as the code's value rather than as something that can be configured.
            "temperature": TEMPERATURE,
            "reasoning_effort": effort or None,
            "reasoning_effort_operations": sorted(REASONING_EFFORT_OPERATIONS),
            # The ceiling that actually bites. The daily allowance is the one people quote
            # and the per-minute one is what returns 429 mid-conversation: a single case
            # review spends over 10,000 tokens in 8 seconds.
            "rate_limit_note": "the per-minute token ceiling is the binding limit, not the daily allowance",
            "pii_masking": (os.getenv("PII_MASKING_ENABLED", "true").lower() == "true"),
            "operations": operations,
        },
        "retrieval": {
            "backend": rag_backend(),
            "top_k": rag_top_k(),
            "embedding_backend": embedding_backend(),
            "embedding_model": embedding_model(),
            "embedding_dimension": embedding_dimension(),
            "vector_index": os.getenv("KB_VECTOR_INDEX") or None,
            # Reading the index state, the chunk count and the ACTIVE embedding backend
            # means loading the model, which /admin/rag/health already does. The page
            # calls it directly so this endpoint stays cheap and the two cannot disagree.
            "detail_endpoint": "/admin/rag/health",
        },
        "integrations": {
            "crm": {
                "provider": os.getenv("CRM_PROVIDER") or None,
                "base_url": os.getenv("CRM_BASE_URL") or None,
                "project_key": os.getenv("CRM_PROJECT_KEY") or None,
                "issue_type": os.getenv("CRM_ISSUE_TYPE") or None,
                "credential_set": _is_set("CRM_API_TOKEN"),
                "timeout_seconds": os.getenv("CRM_TIMEOUT_SECONDS") or None,
                "max_retries": os.getenv("CRM_MAX_RETRIES") or None,
            },
            "tracing": {
                "enabled": os.getenv("LANGFUSE_ENABLED", "false").lower() == "true",
                "base_url": os.getenv("LANGFUSE_BASE_URL") or None,
                "credential_set": _is_set("LANGFUSE_SECRET_KEY"),
                # TRUE means prompt and reply TEXT leaves this system to a third party.
                # Surfaced as its own flag because it is a data-protection decision, not a
                # verbosity setting, and nothing else in the product says it out loud.
                "captures_message_text":
                    os.getenv("LANGFUSE_CAPTURE_IO", "false").lower() == "true",
                "known_gap": "retrieval is not traced as its own span, so chunks and scores "
                             "do not appear alongside the call",
            },
            "spend_recording": {
                "enabled": os.getenv("LLM_OBSERVABILITY_ENABLED", "true").lower() == "true",
                # An unpriced model records 0.00 rather than failing, so a model swap can
                # look free. Named here because the Performance & Cost page cannot tell
                # "spent nothing" from "priced nothing".
                "known_gap": "a model with no configured rate records zero cost",
            },
        },
        "delivery": {
            # The most consequential flag on the page: whether anything reaches a real
            # customer. Reported as a mode rather than a boolean because that is how it is
            # configured.
            "outbound_mode": os.getenv("OUTBOUND_DELIVERY_MODE") or "live",
        },
    }
