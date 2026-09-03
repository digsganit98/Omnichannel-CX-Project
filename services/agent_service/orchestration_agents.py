from datetime import datetime, timezone
from enum import StrEnum
import logging
import re

from pydantic import BaseModel, Field

from services.agent_service.cx_agent import CXAgent
from services.agent_service.handoff import needs_human
from services.channel_service.delivery import OutboundDeliveryService
from services.pii_service.masker import mask_text
from services.rag_service.config import rag_top_k
from services.rag_service.groq_generator import GroqGenerator
from services.rag_service.rag_pipeline import RAGPipeline
from services.ticket_service.ticket_manager import TicketManager
from shared.schemas.intents import Intent, IntentResult
from shared.schemas.messages import InboundMessage
from shared.schemas.tickets import SERVICEABLE_TICKET_STATUSES, Ticket, TicketStatus


logger = logging.getLogger(__name__)


MANUAL_REVIEW_INTENTS = {
    Intent.FRAUD_REPORT,
    Intent.TRANSACTION_DISPUTE,
    # insurance_claim removed: "How do I file a claim?" is a KB FAQ, not always an escalation.
    # Claim filing now escalates only via Rules 7/8 when KB confidence is too low to answer.
    Intent.LOAN_DEFAULT_NOTICE,
    Intent.COMPLAINT,
    Intent.HUMAN_ESCALATION,
}

# Pure informational lookups where the system has real customer data to return via Neo4j.
# Never create tickets for these regardless of urgency or sentiment — high urgency on a
# status query means the customer is anxious, not that an incident needs tracking.
# GENERAL_INQUIRY is excluded: KB may not have the answer, and Rule 7 must be able to
# create a ticket when the system genuinely cannot help.
INFORMATIONAL_INTENTS = {
    Intent.LOAN_STATUS,
    Intent.CLAIM_STATUS,
    Intent.POLICY_STATUS,
}

# Intents that require access to the customer's own account/product data. A sender who
# does not match a real BFSI customer record cannot be safely answered on these — general
# FAQs (loan_application, general_inquiry, human_escalation, fraud_report, complaint, ...)
# stay open to anyone since they don't expose or act on personal account data.
ACCOUNT_VERIFICATION_REQUIRED_INTENTS = {
    Intent.ACCOUNT_BALANCE_INQUIRY,
    Intent.TRANSACTION_DISPUTE,
    Intent.FUND_TRANSFER,
    Intent.LOAN_STATUS,
    Intent.LOAN_DEFAULT_NOTICE,
    Intent.POLICY_STATUS,
    Intent.CLAIM_STATUS,
    Intent.CARD_MANAGEMENT,
    Intent.KYC_UPDATE,
    Intent.TICKET_STATUS,
}


def _is_real_bfsi_customer(graph_ctx: dict) -> bool:
    """True only for a genuinely seeded BFSI customer, not a bare phantom portal node.

    A real customer carries profile identity (name/segment) and/or actual product holdings.
    A phantom `cust_…` node created for an unmatched portal signup has a customer_id but
    name=None, no segment, and empty product lists — it must be treated as unregistered.
    """
    if graph_ctx.get("name") or graph_ctx.get("segment"):
        return True
    return any(
        graph_ctx.get(k)
        for k in ("loans", "claims", "policies", "credit_cards", "accounts", "fixed_deposits")
    )


class QueryResolution(BaseModel):
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    contexts: list[dict] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    llm: dict = Field(default_factory=dict)
    retrieval_backend: str = "unknown"
    retrieval_error: str | None = None
    # L1 (auto-resolvable) / L2 (assisted resolution) / L3 (critical escalation) decision
    # from services.resolution_service — see QueryResolutionAgent._attach_resolution_decision
    # and TicketCreationAgent._escalation_reason for how this drives ticket routing.
    resolution_decision: dict | None = None


class TicketDecision(BaseModel):
    """Two decisions that are currently the same value, deliberately named apart.

    `required` has always answered TWO questions at once: does a ticket exist, and does a
    human review the reply? `review_gate.py` gates the hold on it, so they cannot disagree —
    which was the point, but it also means there is no way to say "this is a distinct matter,
    and no human is needed". That is the common case: a customer asking why a claim was
    rejected needs a thread id and no person.

    `hold_required` is that second question, named separately so the review gate stops reading
    the ticket question. It DEFAULTS to `required`, so behaviour is identical today; a later
    phase can make ticket creation unconditional without touching the hold.
    """

    required: bool
    reason: str | None = None
    # None means "same as required" - see model_post_init below.
    hold_required: bool | None = None

    def model_post_init(self, __context) -> None:
        if self.hold_required is None:
            object.__setattr__(self, "hold_required", self.required)


class TicketAction(StrEnum):
    NONE = "none"
    CLOSE = "close"


class TicketActionDecision(BaseModel):
    action: TicketAction = TicketAction.NONE
    reason: str | None = None


class TicketSelection(BaseModel):
    """Result of disambiguating WHICH open ticket a resolution action applies to.

    Kept separate from the actual close step (TicketCreationAgent.close_ticket) so the
    resolution node stays a single-purpose "mark this ticket resolved" action, and all the
    branching lives here instead.
    """

    target_ticket_id: str | None = None
    needs_clarification: bool = False
    candidates: list[dict] = Field(default_factory=list)
    reason: str | None = None


class CustomerValidationResult(BaseModel):
    is_registered: bool = True
    validation_required: bool = False
    reason: str | None = None


# ── Customer Validation ──────────────────────────────────────────────────────

class CustomerValidationAgent:
    """Confirms the sender is a known BFSI customer before account-specific intents proceed.

    Runs after intent classification (so it knows whether the request actually needs
    personal account data) and before query resolution / ticket creation. General intents
    not in ACCOUNT_VERIFICATION_REQUIRED_INTENTS are always allowed through regardless of
    registration status, so FAQs stay answerable by anyone.
    """

    name = "customer_validation_agent"

    def __init__(self, neo4j_client=None) -> None:
        self.neo4j_client = neo4j_client

    def validate(self, intent: Intent | None, context: dict) -> CustomerValidationResult:
        if intent is None or intent not in ACCOUNT_VERIFICATION_REQUIRED_INTENTS:
            return CustomerValidationResult(is_registered=True, validation_required=False)
        if not self.neo4j_client:
            # No BFSI customer master reachable — fail open, we have no way to verify either way.
            return CustomerValidationResult(
                is_registered=True, validation_required=False, reason="neo4j_unavailable_skip_validation"
            )
        graph_ctx = context.get("graph_context") or {}
        # Registered ONLY if this is a REAL seeded BFSI customer — not merely any node with a
        # customer_id. A phantom portal node (cust_… with name=NULL and no products) has a
        # customer_id but no real profile; it must NOT pass validation, or an unverified user
        # gets a generic LLM answer + ticket instead of the clean reject-unregistered message.
        if graph_ctx.get("customer_id") and _is_real_bfsi_customer(graph_ctx):
            return CustomerValidationResult(is_registered=True, validation_required=True)
        return CustomerValidationResult(
            is_registered=False, validation_required=True, reason="no_matching_bfsi_customer_record"
        )


# ── Agent 1: Intent Classification ──────────────────────────────────────────

class IntentClassificationAgent:
    """Classifies a BFSI message and enriches context with Neo4j customer graph."""

    name = "intent_classification_agent"

    def __init__(self, classifier: CXAgent | None = None, neo4j_client=None) -> None:
        self.classifier = classifier or CXAgent()
        self.neo4j_client = neo4j_client

    def run(self, message: InboundMessage, context: dict) -> IntentResult:
        if self.neo4j_client:
            try:
                from services.neo4j_service.queries import get_customer_context, get_customer_context_by_id
                graph_customer_id = message.metadata.get("portal_graph_customer_id")
                graph_ctx = (
                    get_customer_context_by_id(self.neo4j_client, str(graph_customer_id))
                    if graph_customer_id
                    else get_customer_context(self.neo4j_client, message.channel_identifier)
                )
                if graph_ctx:
                    context = {**context, "graph_context": graph_ctx}
            except Exception:
                pass
        result = self.classifier.analyze(message.text, context)
        # Post-classification fix: small LLMs often label "I applied X weeks ago, any update?"
        # as loan_application when it is clearly a status check on an existing application.
        # Override to loan_status when the customer already has loans and the message uses
        # past-tense applied + update/status/decision/wait keywords.
        if result.intent == Intent.LOAN_APPLICATION:
            existing_loans = context.get("graph_context", {}).get("loans", [])
            if existing_loans:
                txt = message.text.lower()
                status_keywords = {
                    "update", "status", "decision", "heard", "waiting", "delay",
                    "no news", "how long", "when will", "any news", "any update",
                    "answer", "approved", "rejected", "disbursed", "sanctioned",
                    "get a response", "hear back", "still waiting",
                }
                if any(kw in txt for kw in status_keywords):
                    result = result.model_copy(update={"intent": Intent.LOAN_STATUS})
        # Mirror fix for insurance_claim: "What happened with my claim?" should be claim_status
        # (checking an existing claim), not insurance_claim (starting a new filing).
        if result.intent == Intent.INSURANCE_CLAIM:
            existing_claims = context.get("graph_context", {}).get("claims", [])
            if existing_claims:
                txt = message.text.lower()
                status_keywords = {"status", "update", "what happened", "progress", "approved", "rejected", "decided", "paid", "settled"}
                if any(kw in txt for kw in status_keywords):
                    result = result.model_copy(update={"intent": Intent.CLAIM_STATUS})
        # Post-classification fix: customers checking on an existing ticket often use generic
        # phrasing ("any pending status", "anything pending on my end") that doesn't hit the
        # ticket_status keyword list and lands as a low-confidence general_inquiry. Rule 5
        # (low_intent_confidence) then escalates that into a brand-new ticket instead of Rule 3
        # answering from the ticket that already exists. If the customer already has an open
        # ticket and uses generic status/pending wording, treat it as a ticket_status lookup.
        if result.intent == Intent.GENERAL_INQUIRY and (context.get("active_ticket") or context.get("customer_tickets")):
            txt = message.text.lower()
            status_keywords = {
                "pending", "status", "update", "follow up", "follow-up",
                "ticket", "case", "reference", "outstanding", "in progress",
            }
            if any(kw in txt for kw in status_keywords):
                result = result.model_copy(update={"intent": Intent.TICKET_STATUS})
        return result


# ── Agent 2: Query / Complaint Resolution ───────────────────────────────────

# Intents whose answers are PROCEDURAL — the steps are the same for every customer, so a
# verified answer is safely reusable across customers. Deliberately excluded: anything whose
# answer carries the customer's own figures or case specifics (account_balance_inquiry,
# transaction_dispute, loan_status, claim_status, ticket_status...), plus fraud_report and
# human_escalation, where a cached reply must never stand in for a live assessment.
#
# general_inquiry is excluded too, and for a different reason: it is a CATCH-ALL. Two
# questions with nothing in common land on the same key, so a verified answer about account
# charges would be served to someone asking what an SIP is — which is precisely what
# test_general_inquiry_resolution_memory_does_not_override_kb_rag exists to prevent. An
# intent only belongs here when the intent itself pins down the question.
MEMORY_ELIGIBLE_INTENTS = {
    Intent.KYC_UPDATE.value,
}


class QueryResolutionAgent:
    """Routes to ticket lookup, Neo4j (transactional), or RAG/KB based on intent."""

    name = "query_resolution_agent"

    def __init__(self, rag: RAGPipeline | None = None, neo4j_client=None, resolution_engine=None) -> None:
        self.rag = rag or RAGPipeline()
        self.neo4j_client = neo4j_client
        # Injectable like every other external dependency here (rag, neo4j_client) so tests
        # can supply a stub instead of hitting real OpenSearch/Groq. None means "construct the
        # real ResolutionDecisionEngine lazily on first use" via services.resolution_service.
        self.resolution_engine = resolution_engine

    def run(self, message: InboundMessage, context: dict, intent: str | None = None) -> QueryResolution:
        resolution = self._resolve(message, context, intent)
        return self._attach_resolution_decision(message, context, intent, resolution)

    def _resolve(self, message: InboundMessage, context: dict, intent: str | None = None) -> QueryResolution:
        channel = context.get("channel", "")

        # ── Priority 0: ResolutionMemory cache (agent-verified cross-customer answers) ──
        # An answer a human agent approved for THIS KIND of problem, reused for another
        # customer with the same problem. Verified = a human sent it unedited.
        #
        # This gate was previously `intent not in {every Intent value}`, which can never be
        # true — the cache was switched off for every real message. It was disabled on
        # purpose: keyed on the customer's own product id, a hit could serve one customer's
        # particulars ("your outstanding is Rs.91,822") to somebody else. Two changes make
        # it safe to run: memories are now keyed by ticket_scope (the kind of problem), and
        # only intents whose answers are PROCEDURAL are eligible — anything whose answer
        # embeds an amount, a balance or a case's specifics stays excluded and is answered
        # live from the graph/KB below.
        if intent in MEMORY_ELIGIBLE_INTENTS and self.neo4j_client:
            try:
                from services.neo4j_service.query_library import search_resolution_memory
                # Keyed on THIS question's intent, never on whatever ticket the customer
                # happens to have open. An earlier version read the active ticket's
                # ticket_scope, so a customer with an open transaction_dispute asking about
                # KYC looked up "transaction_dispute:atm" and could never find the verified
                # kyc_update answer sitting beside it. The write side still records the
                # ticket's own scope — a memory formed FOR a case belongs to that case —
                # but a lookup must follow what is being asked now.
                memory = search_resolution_memory(self.neo4j_client, f"{intent}:general")
                if memory and memory.get("verified") and memory.get("resolution"):
                    cached_answer = memory["resolution"]
                    return QueryResolution(
                        answer=cached_answer,
                        confidence=0.92,
                        contexts=[{
                            "text": cached_answer,
                            "score": 0.92,
                            "metadata": {
                                "source": "resolution_memory_cache",
                                "doc_type": "customer_graph",
                                "times_reused": memory.get("times_reused", 0),
                                "memory_key": f"{intent}:general",
                                "intent_type": intent,
                                # Fix 66's trap: the provenance panel reads THIS dict, not
                                # retrieval_backend on the object, so the key must be here too.
                                "retrieval": "resolution_memory_cache",
                            },
                        }],
                        citations=[{"index": 1, "source": "resolution_memory_cache", "score": 0.92}],
                        retrieval_backend="resolution_memory_cache",
                    )
            except Exception:
                pass

        # ── Priority 1: Ticket status lookup (cross-channel memory) ──────────
        # Always answer here for TICKET_STATUS — including when the customer genuinely has
        # NO open tickets. _format_ticket_status already has a friendly "no open requests"
        # message for the empty case; the previous `if tickets:` guard skipped straight past
        # it whenever the list was empty, falling through to Neo4j/RAG instead. RAG has no
        # concept of "this customer's tickets" at all, so on a KB miss (or a missing/empty
        # index) it returned a generic "I'm having trouble accessing that" apology AND
        # triggered a fresh escalation ticket — which is exactly what a customer asking
        # "what's my ticket status?" should never see: a confusing new ticket number instead
        # of either their real tickets or a clear "you have none right now".
        if intent == Intent.TICKET_STATUS:
            tickets = context.get("customer_tickets", [])
            raw_text = _format_ticket_status(tickets, channel)
            ticket_ctx = [{
                "text": raw_text,
                "score": 0.98,
                "metadata": {
                    "source": "customer_ticket_lookup",
                    "doc_type": "customer_data",
                    # Same trap Fix 66 found in the Neo4j branch: retrieval_backend below
                    # is set on the QueryResolution OBJECT, but the provenance endpoint
                    # reads this metadata dict (persisted verbatim by
                    # add_retrieval_evidence). Without this key the backend was dropped at
                    # the DB boundary and the panel labelled a ticket read as a KB answer.
                    "retrieval": "customer_ticket_lookup",
                },
            }]
            # Route through Groq so the LLM produces a natural sentence
            # ("Your home loan query is with our Loans team…") instead of a raw bullet list.
            generation = self.rag.generator.generate_answer(message.text, ticket_ctx, context)
            return QueryResolution(
                answer=generation.get("text") or raw_text,
                confidence=0.98,
                contexts=ticket_ctx,
                citations=[{"index": 1, "source": "customer_ticket_lookup", "score": 0.98}],
                retrieval_backend="customer_ticket_lookup",
                llm={
                    "model": generation.get("model"),
                    "llm_used": generation.get("llm_used", False),
                },
            )

        # ── Priority 2: the customer's own records ───────────────────────────
        # The gate here used to be `intent in TRANSACTIONAL_INTENTS`, so 9 of 16 intents
        # reached this branch and returned nothing - a KYC question, a complaint, a general
        # enquiry got no customer data at all, however plainly the answer sat in the graph.
        # A 2-3 word classification decided which of a customer's records existed.
        #
        # The gate is gone. What survives is a data check: if this customer has records, use
        # them; if they have none, fall through to the knowledge base. That is a fact about
        # the customer rather than a guess about their question, so a misclassified message
        # can no longer hide a record from the answer.
        if self.neo4j_client:
            try:
                from services.neo4j_service.queries import neo4j_answer
                graph_ctx = context.get("graph_context", {})
                customer_id = graph_ctx.get("customer_id", "")
                if customer_id:
                    raw_data = neo4j_answer(self.neo4j_client, intent, customer_id)
                    if raw_data:
                        neo4j_ctx = [{
                            "text": raw_data,
                            "score": 0.95,
                            "metadata": {
                                "source": "neo4j_customer_graph",
                                "doc_type": "customer_graph",
                                # Persisted verbatim by add_retrieval_evidence and read back
                                # by the provenance endpoint, which keys on "retrieval". The
                                # RAG paths set it (opensearch_vector / keyword_fallback);
                                # without it here the graph branch stored no backend at all,
                                # so the panel fell back to guessing from the intent label.
                                "retrieval": "neo4j_graph",
                            },
                        }]
                        # The knowledge base as WELL as the records, not instead of them.
                        # This branch used to return here, and Priority 3 below never ran -
                        # fine while a TRANSACTIONAL_INTENTS gate meant only account
                        # questions reached it. With the gate gone the branch fires for
                        # every customer who HAS records, including on questions whose
                        # answer is a procedure rather than a figure: "how do I file a
                        # claim?" would be answered from her three existing claims, having
                        # never seen the filing process the KB holds.
                        #
                        # Both sources go to the model and it uses what answers the
                        # question. Records first, because a question about this customer
                        # should be answered about THIS customer where both could apply.
                        # RETRIEVAL only. rag.answer() would also call generate_answer
                        # internally (rag_pipeline.py:49) and hand back a finished reply -
                        # which this branch then discards and regenerates, costing a second
                        # LLM call on every message. Against a 1000-request/day budget and
                        # ~8 calls per message already, that is a wasted call per customer
                        # message for nothing.
                        kb_ctx = []
                        try:
                            kb_ctx = self.rag.store.similarity_search(message.text, k=rag_top_k()) or []
                        except Exception:
                            # Logged, not silent. A bare swallow here hid the KB going
                            # missing entirely: a rag object without a `store` raises
                            # AttributeError, the except caught it, and every reply was
                            # generated from the customer's records alone with nothing on
                            # screen or in the logs to say the knowledge base had dropped
                            # out. Found when a test's fake had no store.
                            logger.warning("kb_retrieval_failed_in_graph_branch", exc_info=True)
                            kb_ctx = []
                        combined_ctx = neo4j_ctx + kb_ctx
                        # Pass through Groq so the LLM produces a natural CS response
                        # rather than returning raw field=value database output.
                        generation = self.rag.generator.generate_answer(
                            message.text, combined_ctx, context
                        )
                        return QueryResolution(
                            answer=generation.get("text") or raw_data,
                            confidence=0.95,
                            contexts=combined_ctx,
                            citations=[{"index": 1, "source": "neo4j_customer_graph", "score": 0.95}],
                            # Deliberately still neo4j_graph, not a new "hybrid" value: two
                            # escalation rules key on this field (Rule 7's exemption and
                            # _answered_from_customer_record's L2 gate, both via
                            # CUSTOMER_RECORD_BACKENDS). A new value would silently change
                            # when replies are held for a human, which is not what adding
                            # KB passages is meant to do.
                            retrieval_backend="neo4j_graph",
                            llm={
                                "model": generation.get("model"),
                                "llm_used": generation.get("llm_used", False),
                            },
                        )
            except Exception:
                pass

        # ── Priority 3: RAG / Knowledge Base ──────────────────────────────────
        rag_context = {**context, "neo4j_attempted": bool(intent and self.neo4j_client)}
        return QueryResolution(**self.rag.answer(message.text, rag_context))

    def _attach_resolution_decision(
        self,
        message: InboundMessage,
        context: dict,
        intent: str | None,
        resolution: QueryResolution,
    ) -> QueryResolution:
        """Attach the L1/L2/L3 resolution-level decision to every resolved query.

        This runs regardless of which priority branch answered the query (cache, ticket
        lookup, Neo4j, or RAG) so TicketCreationAgent can apply it uniformly downstream.
        """
        try:
            if self.resolution_engine is not None:
                decision = self.resolution_engine.resolve_query_level(
                    message.text, intent or "unknown", context.get("sentiment", "neutral"),
                )
            else:
                from services.resolution_service import resolve_query_level
                decision = resolve_query_level(
                    message.text, intent or "unknown", context.get("sentiment", "neutral"),
                )
            return resolution.model_copy(update={"resolution_decision": decision})
        except Exception as exc:
            return resolution.model_copy(update={
                "resolution_decision": {
                    "intent": intent or "unknown",
                    "sentiment": context.get("sentiment", "neutral"),
                    "resolution_level": "L2",
                    "confidence": 0.35,
                    "reason": f"Resolution decision engine unavailable; assisted review selected. {exc}",
                }
            })


def _format_ticket_status(tickets: list[dict], channel: str = "") -> str:
    """Format open tickets as a natural-language status response."""
    if not tickets:
        return "I could not find any open support requests for your account."

    if channel == "whatsapp":
        # Brief format for WhatsApp
        lines = [f"Here {'is' if len(tickets) == 1 else 'are'} your open support request(s):"]
        for t in tickets:
            sla = _relative_time(t.get("sla_due_at"))
            lines.append(
                f"- Ref: {t['ticket_id']} | {t['intent'].replace('_', ' ').title()} | "
                f"Status: {t['status'].upper()} | Team: {t['assigned_team'].replace('_', ' ').title()}"
                + (f" | Due: {sla}" if sla else "")
            )
        return "\n".join(lines)
    else:
        # Structured format for email / default
        lines = ["Here is a summary of your open support request(s):\n"]
        for t in tickets:
            sla = _relative_time(t.get("sla_due_at"))
            lines.append(f"Reference: {t['ticket_id']}")
            lines.append(f"Type: {t['intent'].replace('_', ' ').title()}")
            lines.append(f"Status: {t['status'].upper()}")
            lines.append(f"Assigned to: {t['assigned_team'].replace('_', ' ').title()}")
            if sla:
                lines.append(f"Expected resolution: {sla}")
            if t.get("escalation_reason"):
                lines.append(f"Reason for escalation: {t['escalation_reason'].replace('_', ' ')}")
            lines.append("")
        lines.append("Our team is working on your request. We will contact you once there is an update.")
        return "\n".join(lines)


def _relative_time(iso_str: str | None) -> str:
    """Convert ISO timestamp to a human-readable relative time string."""
    if not iso_str:
        return ""
    try:
        due = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = due - now
        hours = int(diff.total_seconds() / 3600)
        if hours < 0:
            return "overdue"
        if hours < 1:
            return "within the hour"
        if hours < 24:
            return f"within {hours} hour(s)"
        return f"within {hours // 24} day(s)"
    except Exception:
        return ""


# ── Agent 3: Ticket Creation ─────────────────────────────────────────────────

# Matches this codebase's ticket id format (shared.utils.ids.new_id("tkt") -> "tkt_<12 hex>"),
# tolerant of shorter fragments a customer might paste/retype.
TICKET_ID_PATTERN = re.compile(r"\btkt_[a-f0-9]{6,}\b", re.IGNORECASE)


class TicketCreationAgent:
    """Decides when a JIRA ticket is needed and creates it."""

    name = "ticket_creation_agent"

    def __init__(self, tickets: TicketManager, generator: GroqGenerator | None = None) -> None:
        self.tickets = tickets
        self.generator = generator or GroqGenerator()

    def decide(self, analysis: IntentResult, resolution: QueryResolution, context: dict | None = None,
               message: InboundMessage | None = None) -> TicketDecision:
        """Two independent answers, from one escalation judgement.

        PHASE 4 of the ticket-model redesign. `required` used to be `reason is not None`,
        which made a ticket exist only when a human was needed - so the common case ("this
        is a distinct matter, nobody needs to look at it") had no vocabulary, and the admin
        UI, which groups a conversation by ticket_id, could not group it. Every unticketed
        exchange rendered as its own disconnected box however obviously related.

        Now a ticket ALWAYS exists (it is the name of a matter), and the escalation rules -
        entirely unchanged - decide only the HOLD. The two questions were never the same
        question; Phase 1 split the field so this line could stop conflating them.
        """
        reason = self._escalation_reason(analysis, resolution, context or {}, message)
        return TicketDecision(
            required=True,                     # a ticket is a grouping id: always
            hold_required=reason is not None,  # a human is needed: unchanged rules
            reason=reason,
        )

    def detect_action(self, message: InboundMessage, context: dict) -> TicketActionDecision:
        if not context.get("active_ticket"):
            return TicketActionDecision()

        # Fast keyword check first (no LLM cost for clear cases).
        text = message.text.lower()
        has_close_action = any(phrase in text for phrase in ("close", "resolve", "mark as resolved"))
        has_ticket_context = any(phrase in text for phrase in ("ticket", "case", "query", "request", "issue", "problem"))
        has_resolution_cue = any(phrase in text for phrase in ("resolved", "fixed", "sorted", "done", "all good", "no longer", "thanks", "thank you"))
        # Require close_action + ticket_context, OR resolution_cue + ticket_context.
        # The original triple-AND was too strict — "My issue is sorted, thanks" never matched.
        if has_ticket_context and (has_close_action or has_resolution_cue):
            return TicketActionDecision(action=TicketAction.CLOSE, reason="customer_confirmed_closure")

        # LLM fallback for ambiguous messages (e.g., "All good now", "Issue is sorted").
        try:
            masked_text, _ = mask_text(message.text)
            result = self.generator._generate(
                system_prompt="You are a resolution detector. Answer only YES or NO.",
                user_prompt=(
                    f"Customer message: \"{masked_text}\"\n"
                    "Does this message indicate that the customer's issue has been resolved "
                    "and they no longer need support? Answer YES or NO only."
                ),
                # Without this the call recorded under the unlabelled 'llm_generation'
                # default, so a real production step was invisible in the analytics
                # breakdown — it looked like stray test traffic rather than the
                # resolution detector running on ambiguous messages.
                operation="ticket_action_detection",
            )
            if result.get("llm_used") and result.get("text", "").strip().upper().startswith("YES"):
                return TicketActionDecision(action=TicketAction.CLOSE, reason="llm_confirmed_closure")
        except Exception:
            pass

        return TicketActionDecision()

    def select_ticket(self, message: InboundMessage, context: dict) -> TicketSelection:
        """Work out WHICH open ticket a confirmed resolution action applies to.

        Deliberately separate from close_ticket(): this method only decides the target
        (or that the customer must be asked), so the actual close step stays a clean,
        single-purpose "mark this ticket resolved" action.

        1. If the customer named a ticket id in their message, honor it directly (as long as
           it's actually one of their own open tickets).
        2. Otherwise, look across ALL the customer's open tickets (any channel — an
           omnichannel customer may have opened one on WhatsApp and another by email) for
           ones "of the same kind" as this conversation's active ticket: same intent, and
           same ticket_scope subtype when the active ticket has one (e.g. "card" vs "upi"
           transaction disputes are different matters even though both are
           transaction_dispute).
        3. Exactly one match -> that's the target. Two or more -> ask the customer which one.
        """
        active_ticket = context.get("active_ticket")
        customer_tickets = context.get("customer_tickets") or []

        named_ids = TICKET_ID_PATTERN.findall(message.text or "")
        if named_ids:
            wanted = named_ids[0].lower()
            owned_ids = {t.get("ticket_id", "").lower(): t.get("ticket_id") for t in customer_tickets}
            if active_ticket:
                owned_ids.setdefault(active_ticket.get("ticket_id", "").lower(), active_ticket.get("ticket_id"))
            if wanted in owned_ids:
                return TicketSelection(target_ticket_id=owned_ids[wanted], reason="customer_named_ticket_id")

        if not active_ticket:
            return TicketSelection(reason="no_active_ticket")

        active_intent = active_ticket.get("intent")
        active_scope = (active_ticket.get("metadata") or {}).get("ticket_scope")
        same_kind = [
            t for t in customer_tickets
            if t.get("intent") == active_intent
            and (active_scope is None or (t.get("metadata") or {}).get("ticket_scope") == active_scope)
        ]
        if not same_kind:
            # active_ticket wasn't present in customer_tickets (e.g. it's the only one, or
            # the customer_tickets lookup is limited) — it's still a valid single match.
            same_kind = [active_ticket]

        if len(same_kind) == 1:
            return TicketSelection(target_ticket_id=same_kind[0]["ticket_id"], reason="single_match")

        return TicketSelection(
            needs_clarification=True, candidates=same_kind, reason="multiple_open_tickets_same_kind"
        )

    def close_ticket(self, ticket_id: str) -> Ticket:
        updated = self.tickets.update_status(ticket_id, status=TicketStatus.CLOSED, actor="customer_message")
        return Ticket(**updated)

    def create_or_get(
        self,
        conversation_id: str,
        customer_id: str,
        message: InboundMessage,
        analysis: IntentResult,
        decision: TicketDecision,
        customer: dict,
        graph_context: dict | None = None,
    ) -> Ticket:
        return self.tickets.create_or_get_ticket(
            conversation_id,
            customer_id,
            message,
            analysis.intent,
            analysis.urgency,
            escalation_reason=decision.reason,
            customer=customer,
            sentiment=analysis.sentiment,
            graph_context=graph_context,
            # Phase 4: the hold decides the status. No hold -> LOGGED, a grouping id nobody
            # is working. A hold -> OPEN, a case a human is on. An existing thread that now
            # needs a person is PROMOTED logged -> open inside create_or_get_ticket.
            hold_required=bool(decision.hold_required),
        )

    @staticmethod
    def _escalation_reason(analysis: IntentResult, resolution: QueryResolution, context: dict,
                           message: InboundMessage | None = None) -> str | None:
        # Rule 0: L1/L2/L3 resolution-level decision — DELIBERATELY CHECKED FIRST, before every
        # intent-based rule below (including ones that otherwise say "never escalate", such as
        # Rule 3 ticket_status or Rule 3b informational intents). The resolution engine looks at
        # the actual query content — not just the intent label — so a genuinely critical or
        # customer-specific case must escalate even for an intent that's normally auto-answered.
        # Only fall through to the intent-based rules below when the level is L1.
        decision = resolution.resolution_decision or {}
        level = str(decision.get("resolution_level", "")).upper()
        if level == "L3":
            return f"critical_escalation:{analysis.intent.value}"
        # L2 means "needs customer-specific data or an operational check". That is only a
        # reason to involve a human when we could NOT get that data. When the customer's own
        # record answered the question (the graph, or their own ticket), holding the correct
        # answer for review adds a wait and no accuracy — the agent would read the same record.
        # L3 stays unconditional: risk always reaches a human regardless of how well we answered.
        if level == "L2":
            # Two different things arrive as "L2" — L2's own definition says so: "a backend/data
            # lookup specific to this customer" AND "operational approval". Fix 117 made the gate
            # ask "did the customer's record answer this?", which is right for the lookup half:
            # holding a correct card limit or premium date helps nobody. It is wrong for the other
            # half. "I need this claim honoured, I have hospital bills pending" was answered from
            # the graph — accurately — and auto-sent, because the gate saw a good answer. She was
            # not asking for data. Retrieval cannot honour a claim; only a person can. And no rule
            # below catches it: claim_status is INFORMATIONAL, so Rule 3b returns None on the
            # label alone, and the label is identical to "why was my claim rejected?", which
            # genuinely is a lookup. The distinction lives in the message text, which only the
            # resolution classifier reads — so it is made there and read here.
            if decision.get("l2_kind") == "action":
                return f"approval_required:{analysis.intent.value}"
            if not _answered_from_customer_record(resolution, context):
                return f"assisted_resolution_required:{analysis.intent.value}"

        # Rule 1: Customer explicitly asked for human
        if analysis.intent == Intent.HUMAN_ESCALATION:
            return "customer_requested_human"

        # Rule 2: Intents that always require manual review
        if analysis.intent in MANUAL_REVIEW_INTENTS:
            return f"manual_review_required:{analysis.intent.value}"

        # Rule 2b: Moving money needs a human. Narrowed from {balance, transfer}: escalating a
        # balance question sent the customer a holding message and a wait for an answer the
        # agent could not give either — this system has no core-banking feed, so nobody on
        # this side can see a live balance. The graph branch now says so directly and the
        # reply is auto-sent. fund_transfer stays: it is a request to ACT on money, not to
        # read it, and that warrants a person regardless of what we can retrieve.
        if analysis.intent == Intent.FUND_TRANSFER:
            return "no_live_banking_data"

        if _is_strong_l1_knowledge_answer(resolution):
            return None

        # Rule 2c: READ THE MESSAGE. Every rule above and below keys off a label - an
        # Intent value, a level, a score - and that is how a real complaint auto-sent on
        # 2026-09-02: "I've uploaded those documents already and nothing has happened.
        # This is unacceptable." classified as claim_status (0.95), which Rule 3b exempts,
        # so no rule could see the words. Sentiment was detected as negative and read by
        # nothing. See services/agent_service/handoff.py for the measurement.
        #
        # Placed HERE deliberately:
        #  - after Rule 0, so credible risk still wins and this cannot downgrade an L3;
        #  - after Rule 2, so an already-escalating intent keeps its own specific reason;
        #  - BEFORE Rules 3/3b, because those return None on the label alone and are
        #    exactly what suppressed the complaint. A content signal must outrank a
        #    category exemption.
        # Fails open (returns None) on any error, so a quota-exhausted or slow model
        # leaves today's behaviour untouched rather than blocking every reply.
        if message is not None and getattr(message, "text", ""):
            handoff_reason, _detail = needs_human(message.text)
            if handoff_reason:
                return f"handoff_{handoff_reason}"

        # Rule 3: Ticket status is a lookup — never create a new ticket
        if analysis.intent == Intent.TICKET_STATUS:
            return None

        # Rule 9 (repeated unresolved query) REMOVED. It counted prior outbound turns on the
        # same intent carrying resolved=0, meaning "we have failed this customer twice". That
        # is not what the flag says: NOTHING sets resolved=1 on a reply. Measured across every
        # outbound turn ever written here — 1 row at 1 (a ticket-closure notice), 20 at 0,
        # 10 NULL — so a correct, well-delivered answer is recorded identically to a failure.
        # The rule was therefore counting REPEATED TOPICS, not repeated failures, and it
        # ticketed a customer whose previous question had been answered correctly.
        #
        # Nothing is lost. Every failure it aimed at is already caught AT THE POINT OF FAILURE,
        # which is strictly better because it does not require the customer to ask twice first:
        # Rule 0 (L2 gate) when the customer's record could not answer, Rule 5 on a weak intent
        # classification, Rule 7 when retrieval found nothing or found it weakly. Rule 9 was the
        # only rule judging failure retrospectively by counting history rather than by reading
        # the answer in hand. Same reasoning as Rules 4 and 6: escalate on the question asked,
        # not on the customer's circumstances.
        #
        # `conversation_turns.resolved` is left in place but is now read by nothing on this
        # path — an effectively dead column, kept because dropping it needs a table rebuild.

        # Rule 3b: Pure informational intents — customer is asking for data, not reporting a
        # problem. High urgency/negative sentiment on a status query means they are anxious,
        # not that an incident needs tracking. A real CS agent would just answer them.
        if analysis.intent in INFORMATIONAL_INTENTS:
            return None

        # Rule 4 (high urgency) REMOVED. Urgency is set by the intent classifier reading TONE —
        # capitals, "urgent", "ASAP". Escalating on it contradicted the system's own stated
        # principle in two places: the L1/L2/L3 prompt ("frustration or urgency in wording does
        # NOT by itself justify L2/L3; the actual content of the query does") and Rule 3b's
        # comment ("high urgency on a status query means the customer is anxious, not that an
        # incident needs tracking"). Rule 3b shielded only three intents, so "URGENT!! what are
        # your FD rates??" was held for a human. Urgency still feeds ticket PRIORITY scoring,
        # which is where a tone signal belongs — it just no longer decides that a ticket exists.

        # Rule 5: Low intent confidence (industry threshold: 0.6)
        if analysis.confidence < 0.6:
            return "low_intent_confidence"

        # Rule 6 (>=3 open tickets, new intent) REMOVED. How many OTHER cases a customer has open
        # says nothing about whether THIS message needs a human: a customer with three open
        # tickets asking "what are your branch timings?" was escalated for being unlucky. The
        # threshold of 3 was never derived from anything. If the new issue genuinely needs a
        # person, the content rules (0, 2, 5, 7) catch it on its own merits. Like urgency, a
        # crowded case load is a PRIORITY signal, not a reason a ticket exists.

        # Rule 7: We have no answer good enough to send. Merged from the former Rules 7 and 8,
        # which asked the same question ("can we actually answer this?") split by an
        # implementation detail — nothing retrieved vs. something retrieved but weak. They
        # carried DIFFERENT exemption lists, so a customer_ticket_lookup returning zero rows
        # escalated while one returning a weak row did not; that asymmetry was unintended.
        # One rule, one exemption list, so the two halves cannot drift apart again.
        if resolution.retrieval_backend not in CUSTOMER_RECORD_BACKENDS:
            if not resolution.contexts:
                return "knowledge_not_found"
            if resolution.confidence < 0.3:
                return "low_retrieval_confidence"

        return None


# ── Backwards-compatible aliases ─────────────────────────────────────────────
# Backends that read the CUSTOMER'S OWN record rather than general knowledge. An answer from
# one of these is customer-specific by construction, which is exactly what L2 asks for.
CUSTOMER_RECORD_BACKENDS = {"neo4j_graph", "customer_ticket_lookup"}


# Collections in graph_context that ARE the customer's own records. Presence of a non-empty
# one means the customer's record set was in the prompt. Deliberately excludes the identity
# fields (name/email/phone/city/segment), which are always present and prove nothing, and
# open_cases, which is ticket state rather than a record that can answer a question.
CUSTOMER_RECORD_COLLECTIONS = (
    "accounts", "credit_cards", "fixed_deposits", "loans", "policies", "claims",
)


def _customer_records_supplied(context: dict | None) -> bool:
    """True when this customer's own records were put in front of the model.

    The customer-context block in groq_generator runs on EVERY message regardless of intent
    and emits whatever graph_context holds, so the records reach the model by that path as
    well as by intent-routed retrieval.
    """
    graph_context = (context or {}).get("graph_context") or {}
    return any(graph_context.get(k) for k in CUSTOMER_RECORD_COLLECTIONS)


def _answered_from_customer_record(resolution: QueryResolution, context: dict | None = None) -> bool:
    """True when the reply was grounded in this customer's own data.

    This asks about GROUNDING, not about which retrieval branch ran. It used to ask only the
    latter - `retrieval_backend in CUSTOMER_RECORD_BACKENDS` - and that backend is set only
    when `intent in TRANSACTIONAL_INTENTS`, so the answer depended on a CLASSIFICATION LABEL.
    Observed live: "What is the amount due on my credit card and by when?" classified as
    general_inquiry, retrieval therefore went to the KB pdf, this returned False, and the
    reply was held for a human - while the reply it held quoted the card's balance and due
    date correctly, because the customer-context block had supplied the record set anyway.
    A misclassification became a false hold on a question the system had already answered.

    So either path counts: the intent-routed retrieval, or the records being supplied. The
    confidence and contexts checks still apply to the retrieval path, because there a low
    score means retrieval genuinely failed.

    Fix 117 is preserved: when the customer's records hold nothing relevant, graph_context
    carries no non-empty collection and this still returns False, so the question is still
    escalated - which is what that rule exists for.
    """
    if resolution.retrieval_backend in CUSTOMER_RECORD_BACKENDS:
        if resolution.contexts and resolution.confidence >= 0.3:
            return True
    return _customer_records_supplied(context)


def _is_strong_l1_knowledge_answer(resolution: QueryResolution) -> bool:
    decision = resolution.resolution_decision or {}
    if str(decision.get("resolution_level", "")).upper() != "L1":
        return False
    if resolution.retrieval_backend == "resolution_memory_cache":
        return False
    if resolution.confidence < 0.3:
        return False
    return any(
        context.get("metadata", {}).get("doc_type") == "knowledge_base"
        for context in (resolution.contexts or [])
    )


IntentDetectionAgent = IntentClassificationAgent
TicketManagementAgent = TicketCreationAgent


class WorkflowAutomationAgent:
    """Thin wrapper kept for backwards compatibility; logic now lives in graph.py."""

    name = "workflow_automation_agent"

    def __init__(self, delivery: OutboundDeliveryService | None = None) -> None:
        self.delivery = delivery or OutboundDeliveryService()

    @staticmethod
    def compose_answer(
        resolution: QueryResolution,
        ticket: Ticket | None,
        channel: str = "",
        customer_name: str = "",
        forked_now: bool = False,
    ) -> str:
        body = _strip_email_boilerplate((resolution.answer or "").strip()) if resolution else ""

        # SERVICEABLE only, not "a ticket exists". Under Phase 4 of the ticket-model
        # redesign every query gets a ticket, so `if ticket:` told a customer asking
        # "what is my card limit?" that their request was "logged under reference tkt_x"
        # and a team "will follow up" - for a question that was answered completely, in
        # full, in the same message. Nobody is following up, and the reference is an
        # internal grouping id they cannot use.
        #
        # This is decision 1 of the redesign: the customer sees a reference only once the
        # thread is serviceable, which is exactly when there IS something to follow up on.
        # It is also the Fix 119 false-reference failure, reappearing through the door the
        # redesign opened. A LOGGED ticket still exists and still groups the conversation -
        # it is simply not mentioned to the customer.
        if ticket and ticket.status in SERVICEABLE_TICKET_STATUSES:
            ref = f"*{ticket.ticket_id}*" if channel == "whatsapp" else ticket.ticket_id
            team = ticket.assigned_team.replace("_", " ")
            if getattr(ticket, "escalation_reason", None) == "customer_requested_human":
                sla_eta = _relative_time(getattr(ticket, "sla_due_at", None))
                eta_clause = f" You will be contacted {sla_eta}." if sla_eta else ""
                ticket_note = (
                    f"Your request has been logged under reference {ref}. "
                    f"Our {team} team will be in touch with you.{eta_clause}"
                )
            else:
                ticket_note = (
                    f"Your request has been logged under reference {ref}. "
                    f"Our {team} team will follow up with you."
                )
            # The referee judged this a separate matter while other threads were live.
            # Saying so is what a human agent does, and it is the one continuity decision
            # the customer needs told: without it they cannot know whether "my dispute"
            # now refers to one case or two, and neither can anyone reading the thread.
            # Only serviceable threads count - announcing a split from a logging id would
            # expose an internal reference (decision 1).
            # `forked_now`, not the ticket's forked_from metadata. The metadata is stored on
            # the TICKET and so stays true for its whole life: reading it here announced the
            # split on every later message of the thread, including ones that plainly
            # continued it and that this same reply then names by reference. Forking is a
            # fact about ONE message; only the message that actually forked should say so.
            if forked_now:
                ticket_note = (
                    "This looks like a separate issue from your existing request, "
                    "so we have raised it on its own. " + ticket_note
                )
            # Skip the appended reference when the reply already gave it. The note exists
            # so every reply carries its ticket id; a reply naming that id already
            # satisfies it, and appending anyway printed it twice ("your dispute tkt_X is
            # being reviewed" / "logged under reference tkt_X"). Started once the generator
            # was told which case a message belongs to, so the model began citing the right
            # id rather than none or a wrong one. A DIFFERENT id in the body does not count:
            # the note is still appended, so a misattributed reply still carries the truth.
            if ticket.ticket_id not in body:
                body = f"{body}\n\n{ticket_note}".strip() if body else ticket_note

        if channel == "email":
            salutation_name = _salutation(customer_name)
            return (
                f"Dear {salutation_name},\n\n"
                f"{body}\n\n"
                "Thank you for reaching out to us. We are committed to resolving your query promptly.\n\n"
                "Warm regards,\nCustomer Support Team"
            )
        # WhatsApp and default: prepend a short greeting with the customer's real name
        # (falls back to "Customer" when no name is known), then the LLM body.
        salutation_name = _salutation(customer_name)
        return f"Hi {salutation_name},\n\n{body}" if body else body

    def send_reply(self, message: InboundMessage, answer: str) -> dict:
        return self.delivery.send(message, answer)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _strip_email_boilerplate(body: str) -> str:
    """Remove LLM-added greetings and sign-offs so the system wrapper doesn't duplicate them."""
    lines = body.splitlines()
    # Strip leading greeting line: "Dear Customer," / "Dear Priya," / "Dear Sir/Madam,"
    if lines and lines[0].lower().strip().startswith("dear "):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    # Strip trailing sign-off block (Warm regards, Best regards, Thank you, etc.)
    sign_off_tokens = ("warm regards", "best regards", "kind regards", "sincerely", "regards,", "thank you", "thanks and")
    while lines and any(lines[-1].lower().strip().startswith(s) for s in sign_off_tokens):
        lines = lines[:-1]
        while lines and not lines[-1].strip():
            lines = lines[:-1]
    return "\n".join(lines).strip()


def _salutation(customer_name: str) -> str:
    """Derive a safe salutation name from the customer's display_name.

    If the only thing we have is an email address, we do NOT actually know the
    person's real name, so we greet them as "Customer" rather than fabricating a
    name from the email local-part (e.g. demoaccforoff@… → "Demoaccforoff"). A
    verified BFSI customer's real name comes from Neo4j (see graph.py display_name
    handling), so they never hit the email branch; only unverified / name-less
    senders fall back to "Customer".
    """
    name = (customer_name or "").strip()
    if not name or "@" in name:
        return "Customer"
    return name


