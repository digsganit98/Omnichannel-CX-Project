from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from services.agent_service.cx_agent import CXAgent
from services.channel_service.delivery import OutboundDeliveryService
from services.pii_service.masker import mask_text
from services.rag_service.groq_generator import GroqGenerator
from services.rag_service.rag_pipeline import RAGPipeline
from services.ticket_service.ticket_manager import TicketManager
from shared.schemas.intents import Intent, IntentResult, Urgency
from shared.schemas.messages import InboundMessage
from shared.schemas.tickets import Ticket, TicketStatus


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
    required: bool
    reason: str | None = None


class TicketAction(StrEnum):
    NONE = "none"
    RESOLVE = "resolve"


class TicketActionDecision(BaseModel):
    action: TicketAction = TicketAction.NONE
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
        # Only for non-sensitive, non-ticket intents. Verified = human agent approved it.
        # Broad ResolutionMemory keys are unsafe for customer-facing FAQs. Until memory
        # hits are semantically validated, let KB/graph retrieval answer the live query.
        memory_excluded_intents = {intent_item.value for intent_item in Intent}
        if intent and intent not in memory_excluded_intents and self.neo4j_client:
            try:
                from services.neo4j_service.query_library import search_resolution_memory
                graph_ctx = context.get("graph_context", {})
                product_id = _derive_product_id_for_memory(intent, graph_ctx)
                memory = search_resolution_memory(self.neo4j_client, product_id, intent)
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
                                "product_id": product_id,
                                "intent_type": intent,
                            },
                        }],
                        citations=[{"index": 1, "source": "resolution_memory_cache", "score": 0.92}],
                        retrieval_backend="resolution_memory_cache",
                    )
            except Exception:
                pass

        # ── Priority 1: Ticket status lookup (cross-channel memory) ──────────
        if intent == Intent.TICKET_STATUS:
            tickets = context.get("customer_tickets", [])
            if tickets:
                raw_text = _format_ticket_status(tickets, channel)
                ticket_ctx = [{
                    "text": raw_text,
                    "score": 0.98,
                    "metadata": {"source": "customer_ticket_lookup", "doc_type": "customer_data"},
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

        # ── Priority 2: Neo4j transactional data (loans, claims, etc.) ───────
        if intent and self.neo4j_client:
            try:
                from services.neo4j_service.queries import neo4j_answer, TRANSACTIONAL_INTENTS
                if intent in TRANSACTIONAL_INTENTS:
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
                                },
                            }]
                            # Pass through Groq so the LLM produces a natural CS response
                            # rather than returning raw field=value database output.
                            generation = self.rag.generator.generate_answer(
                                message.text, neo4j_ctx, context
                            )
                            return QueryResolution(
                                answer=generation.get("text") or raw_data,
                                confidence=0.95,
                                contexts=neo4j_ctx,
                                citations=[{"index": 1, "source": "neo4j_customer_graph", "score": 0.95}],
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

class TicketCreationAgent:
    """Decides when a JIRA ticket is needed and creates it."""

    name = "ticket_creation_agent"

    def __init__(self, tickets: TicketManager, generator: GroqGenerator | None = None) -> None:
        self.tickets = tickets
        self.generator = generator or GroqGenerator()

    def decide(self, analysis: IntentResult, resolution: QueryResolution, context: dict | None = None) -> TicketDecision:
        reason = self._escalation_reason(analysis, resolution, context or {})
        return TicketDecision(required=reason is not None, reason=reason)

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
            return TicketActionDecision(action=TicketAction.RESOLVE, reason="customer_confirmed_resolution")

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
            )
            if result.get("llm_used") and result.get("text", "").strip().upper().startswith("YES"):
                return TicketActionDecision(action=TicketAction.RESOLVE, reason="llm_confirmed_resolution")
        except Exception:
            pass

        return TicketActionDecision()

    def resolve_ticket(self, ticket_id: str) -> Ticket:
        updated = self.tickets.update_status(ticket_id, status=TicketStatus.RESOLVED, actor="customer_message")
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
        )

    @staticmethod
    def _escalation_reason(analysis: IntentResult, resolution: QueryResolution, context: dict) -> str | None:
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
        if level == "L2":
            return f"assisted_resolution_required:{analysis.intent.value}"

        # Rule 1: Customer explicitly asked for human
        if analysis.intent == Intent.HUMAN_ESCALATION:
            return "customer_requested_human"

        # Rule 2: Intents that always require manual review
        if analysis.intent in MANUAL_REVIEW_INTENTS:
            return f"manual_review_required:{analysis.intent.value}"

        # Rule 2b: Intents that need live banking data this system does not have.
        # RAG may return generic KB content that looks like an answer but isn't the
        # customer's actual balance or transfer status — always escalate to a human.
        if analysis.intent in {Intent.ACCOUNT_BALANCE_INQUIRY, Intent.FUND_TRANSFER}:
            return "no_live_banking_data"

        if _is_strong_l1_knowledge_answer(resolution):
            return None

        # Rule 3: Ticket status is a lookup — never create a new ticket
        if analysis.intent == Intent.TICKET_STATUS:
            return None

        # Rule 9: Same intent handled ≥ 2 times (outbound, unresolved) with no active ticket.
        # Only count turns where resolved=False/0 — if prior turns were resolved successfully,
        # the customer asking again is a new check, not an unresolved follow-up.
        # MUST come before Rule 3b so informational intents (loan_status etc.) can still
        # escalate when the system has repeatedly failed to give a useful answer.
        recent_turns = context.get("recent_turns", [])
        repeat_count = sum(
            1 for t in recent_turns
            if (
                t.get("direction") == "outbound"
                and t.get("intent") == analysis.intent.value
                and not t.get("resolved")
            )
        )
        if repeat_count >= 2 and not context.get("active_ticket"):
            return "repeated_unresolved_query"

        # Rule 3b: Pure informational intents — customer is asking for data, not reporting a
        # problem. High urgency/negative sentiment on a status query means they are anxious,
        # not that an incident needs tracking. A real CS agent would just answer them.
        if analysis.intent in INFORMATIONAL_INTENTS:
            return None

        # Rule 4: High urgency
        if analysis.urgency == Urgency.HIGH:
            return "high_urgency"

        # Rule 5: Low intent confidence (industry threshold: 0.6)
        if analysis.confidence < 0.6:
            return "low_intent_confidence"

        # Rule 6: Repeat customer with many open tickets — only escalate if this specific intent
        # is not already covered by an existing ticket (prevents piling on more tickets when
        # the customer is already overwhelmed with open cases).
        customer_tickets = context.get("customer_tickets", [])
        if len(customer_tickets) >= 3:
            existing_intents = {t.get("intent") for t in customer_tickets}
            if analysis.intent.value not in existing_intents:
                return "repeat_customer_new_issue"
            return None  # Existing ticket already covers this intent — no new one needed

        # Rule 7: No knowledge found and not sourced from Neo4j
        if not resolution.contexts and resolution.retrieval_backend != "neo4j_graph":
            return "knowledge_not_found"

        # Rule 8: Very low retrieval confidence (industry threshold: 0.3)
        if resolution.confidence < 0.3 and resolution.retrieval_backend not in (
            "neo4j_graph", "customer_ticket_lookup"
        ):
            return "low_retrieval_confidence"

        return None


# ── Backwards-compatible aliases ─────────────────────────────────────────────
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
    ) -> str:
        body = _strip_email_boilerplate((resolution.answer or "").strip()) if resolution else ""

        if ticket:
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


def _derive_product_id_for_memory(intent: str, graph_ctx: dict) -> str:
    """Derive the product_id key for ResolutionMemory lookup from intent + graph context."""
    if "loan" in intent:
        loans = graph_ctx.get("loans", [])
        return loans[0].get("loan_id", "loan_general") if loans else "loan_general"
    if any(k in intent for k in ("claim", "insurance", "policy")):
        claims = graph_ctx.get("claims", [])
        return claims[0].get("claim_id", "insurance_general") if claims else "insurance_general"
    return "general"
