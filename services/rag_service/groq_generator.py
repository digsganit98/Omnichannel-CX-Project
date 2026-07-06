import json
import os
import time
from pathlib import Path

from services.observability_service import record_llm_call
from services.pii_service.masker import mask_text, unmask_text

# Separator used to mask several text fragments in a single mask_text() call so
# placeholder numbering (PHONE_1, PHONE_2, ...) stays unique across the whole prompt
# instead of colliding if each fragment were masked independently.
_PII_JOIN = "\x00"

_SYSTEM_MD = Path(__file__).resolve().parents[2] / "shared" / "prompts" / "system.md"


def _system_prompt() -> str:
    try:
        return _SYSTEM_MD.read_text(encoding="utf-8").strip()
    except Exception:
        return "You are a BFSI customer support AI."


# ── Intent definitions used in classification prompt ────────────────────────

_INTENT_DEFINITIONS = """
account_balance_inquiry  – Customer wants to know their account balance or recent transactions.
transaction_dispute      – Customer reports an incorrect, unauthorized, or failed transaction.
fund_transfer            – Customer wants to initiate or track a fund transfer.
loan_status              – Customer asking about the status of an existing loan. ALSO use this when the customer says they "applied" weeks/days ago and are asking for an update, decision, or why there is a delay — that is status-checking, NOT a new application.
loan_application         – Customer wants to apply for a NEW loan they have NOT yet submitted. If they already applied and are waiting for news, use loan_status instead.
loan_default_notice      – Customer received or is asking about a loan default or overdue notice.
policy_status            – Customer asking about the status of an existing insurance policy.
claim_status             – Customer asking for the status or progress of an EXISTING claim.
insurance_claim          – Customer asking how to file or submitting a NEW insurance claim.
card_management          – Customer wants to block, replace, or manage their debit/credit card.
kyc_update               – Customer needs to update Know-Your-Customer (KYC) documents.
fraud_report             – Customer is reporting fraud, account hacking, phishing, or stolen money.
complaint                – Customer expressing dissatisfaction not covered by the above intents.
ticket_status            – Customer is asking about the status of an existing support ticket, query, or complaint they raised before. Phrases like "status of my issue", "any update on my request", "follow up on my complaint" → ticket_status.
general_inquiry          – General product/service question that does not fit any specific intent above.
human_escalation         – Customer explicitly asks to speak with a human agent.
""".strip()

# ── Few-shot examples for boundary cases ─────────────────────────────────────

_FEW_SHOT_EXAMPLES = """
Example 1 – loan_status vs loan_application:
  Message: "I applied for a home loan last week, what is the status?"
  → intent: loan_status  (checking existing application, NOT a new request), secondary_intent: null
  Message: "I applied for a home loan 3 weeks ago and have not heard back. When will I get a decision?"
  → intent: loan_status  (waiting for update on existing application), secondary_intent: null
  Message: "I want to apply for a home loan."
  → intent: loan_application  (new application request), secondary_intent: null

Example 1b – claim_status vs insurance_claim:
  Message: "How do I file a health insurance claim?"
  → intent: insurance_claim  (asking about the new-claim process), secondary_intent: null
  Message: "What is the status of my existing claim?"
  → intent: claim_status  (checking an existing claim), secondary_intent: null

Example 2 – complaint vs fraud_report:
  Message: "I'm very unhappy with the charges on my account this month."
  → intent: complaint  (dissatisfaction, not fraud), secondary_intent: null

Example 3 – fraud_report (high urgency):
  Message: "Someone made a ₹50,000 transfer from my account that I didn't authorize!"
  → intent: fraud_report, urgency: high, sentiment: negative, secondary_intent: null

Example 4 – ticket_status (cross-channel follow-up):
  Message: "Hi, what is the status of my issue?"
  → intent: ticket_status, urgency: low, sentiment: neutral, secondary_intent: null

Example 5 – multi-intent (compound query):
  Message: "I want to check my loan status and also report a wrong debit on my account."
  → intent: loan_status, secondary_intent: transaction_dispute

Example 6 – multi-language (Hindi):
  Message: "मेरे लोन की स्थिति क्या है?"
  → intent: loan_status, language: hi, urgency: low

Example 7 – multi-language (Tamil):
  Message: "என் கடன் நிலை என்ன?"
  → intent: loan_status, language: ta, urgency: low
""".strip()

# ── Language name map for multilingual responses ─────────────────────────────

_LANGUAGE_NAMES = {
    "hi": "Hindi", "ta": "Tamil", "te": "Telugu", "kn": "Kannada",
    "ml": "Malayalam", "mr": "Marathi", "bn": "Bengali", "gu": "Gujarati",
    "pa": "Punjabi", "ur": "Urdu", "fr": "French", "es": "Spanish",
    "ar": "Arabic", "zh": "Chinese", "de": "German",
}


class GroqGenerator:
    def __init__(self) -> None:
        self.api_key = os.getenv("GROQ_API_KEY", "")
        self.model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        self.timeout = int(os.getenv("GROQ_TIMEOUT_SECONDS", "30"))
        self._client = None

    @property
    def _groq(self):
        if self._client is None:
            import groq as groq_sdk
            self._client = groq_sdk.Groq(api_key=self.api_key)
        return self._client

    # ── Public interface ─────────────────────────────────────────────────────

    def generate_answer(self, query: str, contexts: list[dict], conversation_context: dict | None = None) -> dict:
        ctx = conversation_context or {}
        channel = ctx.get("channel", "")
        language = ctx.get("language", "en")

        channel_rule = _channel_format_rule(channel)
        lang_rule = ""
        if language and language != "en":
            lang_name = _LANGUAGE_NAMES.get(language, language.upper())
            lang_rule = (
                f"\nLanguage: The customer wrote in {lang_name}. "
                f"Reply in {lang_name}. Keep ticket IDs, amounts, and dates in their original format."
            )

        # No numbered references — avoids the LLM citing "[1]" inline or appending a Sources section.
        sources = "\n\n".join(
            f"[{item.get('metadata', {}).get('source', 'unknown')}]:\n{item['text']}"
            for item in contexts
        )
        graph_ctx_text = _format_graph_context(ctx.get("graph_context"))
        conv_history_text = _format_conversation_history(ctx.get("recent_turns", []))
        # Conversation summary is a raw pipe-delimited log — inject it only when there are
        # no recent_turns to avoid sending redundant and hard-to-parse content to the LLM.
        conv_summary = (ctx.get("conversation_summary") or "").strip() if not conv_history_text else ""

        # Mask PII before it reaches the LLM. All fragments are masked in one call (joined
        # by a separator) so placeholder numbering stays unique across the whole prompt;
        # the mapping is used to restore the customer's own name/phone/email in the answer
        # below, and discarded after — never persisted.
        known_values = _known_values(ctx.get("graph_context"))
        (query, graph_ctx_text, conv_history_text, conv_summary), pii_mapping = _mask_fragments(
            [query, graph_ctx_text, conv_history_text, conv_summary], known_values
        )

        no_data_note = (
            "- IMPORTANT: No customer account context is provided. Do NOT say 'I checked your account' or "
            "imply you have access to account data. Say: 'I am currently unable to access your account "
            "details — let me connect you with our support team.'\n"
            if not graph_ctx_text else ""
        )
        user_prompt = (
            f"{channel_rule}{lang_rule}\n\n"
            "Rules:\n"
            # PROMPT-1: No-ticket-promise and no-citation rules are FIRST — LLMs weight earlier rules more.
            "- CRITICAL: Do NOT invent ticket IDs, loan IDs, claim IDs, or reference numbers. "
            "Only mention a ticket ID if it appears verbatim in the customer data below. "
            "Do NOT say 'your ticket reference is ...' unless that exact ID is shown. "
            "Do NOT say 'I will create a ticket' or 'a ticket will be raised'.\n"
            "- Do NOT add a 'Sources:' or 'References:' section. Do NOT cite sources inline. Just answer.\n"
            # PROMPT-2: No invented timelines.
            "- CRITICAL: Do NOT state a specific processing timeline or turnaround time unless "
            "the ticket SLA or system data explicitly provides one. Do NOT say 'within 5-7 business days' "
            "unless that came from a loan/claim record below.\n"
            "- Answer ONLY the specific question the customer asked. Do NOT volunteer info about "
            "unrelated products (e.g. claims when they asked about loans) unless explicitly asked.\n"
            "- Answer ONLY using the retrieved context and conversation history below. Do NOT invent facts.\n"
            "- If the customer references a prior issue from another channel, find it in the history below.\n"
            "- When account data is provided, present it in natural sentences as a human CS agent would. "
            "Do NOT write 'Status: X' or 'Amount: Y' — say 'Your car loan has been approved' instead.\n"
            "- Address the customer's concern first — acknowledge worry or frustration before giving data.\n"
            "- If context is insufficient, say: 'I need to escalate this to our support team.'\n"
            "- Never mention internal system names like OpenSearch, Neo4j, or RAG.\n"
            + no_data_note
            + "\n"
            + (f"Customer account context:\n{graph_ctx_text}\n\n" if graph_ctx_text else "")
            + (f"{conv_history_text}\n\n" if conv_history_text else "")
            + (f"Conversation summary: {conv_summary}\n\n" if conv_summary else "")
            + f"Customer query: {query}\n\n"
            f"Retrieved context:\n{sources or '(none)'}\n\n"
            "Answer (body only — no greeting, no sign-off):"
        )
        result = self._generate(
            system_prompt=_system_prompt(),
            user_prompt=user_prompt,
            operation="answer_generation",
            metadata={"context_count": len(contexts), "channel": channel},
        )
        if result.get("text"):
            # Restore the customer's own masked values (e.g. name) if the LLM echoed a
            # placeholder back — never send [NAME_1]-style tokens to the customer.
            result = {**result, "text": unmask_text(result["text"], pii_mapping)}
        return result

    def classify_message(self, message: str, context: dict | None = None) -> dict | None:
        ctx = context or {}
        graph_ctx = ctx.get("graph_context")
        graph_text = _format_graph_context(graph_ctx) if graph_ctx else ""

        # Last 3 inbound turns give the classifier conversation context so it can
        # correctly handle follow-ups like "What about the other issue I mentioned?"
        recent = ctx.get("recent_turns", [])
        history_lines = []
        for t in list(reversed(recent))[:6]:
            if t.get("direction") == "inbound":
                history_lines.append(f"  Prior message: {(t.get('text') or '')[:150]}")
                if len(history_lines) >= 3:
                    break
        history_text = "\n".join(history_lines)

        # Mask PII before it reaches the LLM — see generate_answer() for why fragments are
        # masked together in one call rather than independently.
        known_values = _known_values(graph_ctx)
        (message, graph_text, history_text), pii_mapping = _mask_fragments(
            [message, graph_text, history_text], known_values
        )

        user_prompt = (
            "## Intent Definitions\n"
            f"{_INTENT_DEFINITIONS}\n\n"
            "## Few-Shot Examples\n"
            f"{_FEW_SHOT_EXAMPLES}\n\n"
            "## Classification Task\n"
            "Think step by step:\n"
            "1. Detect the customer's language. Set `language` to ISO-639-1 code (e.g. `en`, `hi`, `ta`).\n"
            "2. Identify key entities (product, action, emotion) in the message.\n"
            "3. Match to the PRIMARY intent. IMPORTANT disambiguation rules:\n"
            "   - If the customer says they 'applied' weeks/days ago and are asking for an update, status, or decision → use loan_status (NOT loan_application). Use loan_application ONLY when the customer has NOT yet applied and wants to start a new application.\n"
            "   - If the customer account context shows an existing loan/claim of the same type the customer is asking about, and the message asks for an update/status → use loan_status or claim_status.\n"
            "   - Use recent conversation context (prior messages) to resolve ambiguous follow-ups.\n"
            "4. If the message contains a SECOND distinct request, set `secondary_intent`; otherwise set it to null.\n"
            "5. Determine urgency: high if fraud/stolen/urgent/ASAP/blocked/overdue, "
            "OR if a time-sensitive financial deadline is mentioned (same day or next day — "
            "e.g. court date, property registration, flight, payment due today); "
            "medium if sentiment is negative; low otherwise.\n"
            "6. Return ONLY a JSON object — no explanation, no markdown.\n\n"
            "Required JSON schema:\n"
            '{"intent": "<primary intent>", '
            '"secondary_intent": "<second intent or null>", '
            '"confidence": <0.0–1.0>, '
            '"urgency": "<low|medium|high>", '
            '"sentiment": "<positive|neutral|negative>", '
            '"language": "<ISO-639-1 code>", '
            '"reason": "<one short sentence>"}\n\n'
            + (f"Customer account context:\n{graph_text}\n\n" if graph_text else "")
            + (f"Recent customer messages (for context):\n{history_text}\n\n" if history_text else "")
            + f"Customer message: {message}"
        )

        result = self._generate(
            system_prompt="You are a BFSI intent classifier. Return ONLY valid JSON. Never explain or add markdown.",
            user_prompt=user_prompt,
            operation="intent_classification",
            metadata={"has_graph_context": bool(graph_text), "history_turns": len(history_lines)},
        )
        if not result["llm_used"]:
            return None
        try:
            # Defensive: unmask before parsing in case a placeholder leaked into the
            # "reason" field. intent/urgency/sentiment/language never contain PII.
            text = unmask_text(result["text"].strip(), pii_mapping)
            return json.loads(text[text.find("{") : text.rfind("}") + 1])
        except (json.JSONDecodeError, ValueError):
            return None

    def status(self, check_connection: bool = False) -> dict:
        status: dict = {
            "provider": "groq",
            "model": self.model,
            "timeout_seconds": self.timeout,
            "api_key_configured": bool(self.api_key),
            "reachable": None,
        }
        if not check_connection or not self.api_key:
            return status
        try:
            models = self._groq.models.list()
            status["reachable"] = True
            status["available_models"] = [m.id for m in models.data]
        except Exception as exc:
            status["reachable"] = False
            status["error"] = str(exc)
        return status

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _generate(
        self,
        system_prompt: str,
        user_prompt: str,
        operation: str = "llm_generation",
        metadata: dict | None = None,
    ) -> dict:
        if not self.api_key:
            result = {"text": "", "model": self.model, "llm_used": False, "error": "GROQ_API_KEY not set"}
            record_llm_call(
                provider="groq",
                model=self.model,
                operation=operation,
                llm_used=False,
                latency_ms=0.0,
                input_text=user_prompt,
                error=result["error"],
                metadata=metadata,
            )
            return result
        started = time.perf_counter()
        try:
            response = self._groq.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                timeout=self.timeout,
            )
            text = response.choices[0].message.content.strip()
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            record_llm_call(
                provider="groq",
                model=self.model,
                operation=operation,
                llm_used=True,
                latency_ms=latency_ms,
                response=response,
                input_text=user_prompt,
                output_text=text,
                metadata=metadata,
            )
            return {"text": text, "model": self.model, "llm_used": True}
        except Exception as exc:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            record_llm_call(
                provider="groq",
                model=self.model,
                operation=operation,
                llm_used=False,
                latency_ms=latency_ms,
                input_text=user_prompt,
                error=str(exc),
                metadata=metadata,
            )
            return {"text": "", "model": self.model, "llm_used": False, "error": str(exc)}


# ── Module-level helpers ──────────────────────────────────────────────────────

def _channel_format_rule(channel: str) -> str:
    if channel == "whatsapp":
        return (
            "CHANNEL: WhatsApp\n"
            "Write the response BODY only — greeting and sign-off are added automatically by the system.\n"
            "Rules: max 3–4 lines · first line = one direct answer · "
            "use *bold* (WhatsApp markdown) for ticket IDs, amounts, and status · "
            "bullets only for 3+ items · conversational, no formal salutations."
        )
    if channel == "email":
        return (
            "CHANNEL: Email\n"
            "Write the response BODY only — 'Dear Customer' and 'Thank you / Warm regards' are added "
            "automatically by the system. Do NOT include them yourself.\n"
            "Rules: 1–3 formal paragraphs · first paragraph acknowledges the customer's concern empathetically "
            "and gives the direct answer · second paragraph provides relevant details in natural sentences "
            "(no field=value lists) · last paragraph covers next steps or ticket reference if applicable · "
            "no informal contractions."
        )
    return "Format: Be concise and professional."


def _format_conversation_history(recent_turns: list[dict]) -> str:
    if not recent_turns:
        return ""
    lines = ["Recent conversation history (newest first):"]
    for turn in list(reversed(recent_turns))[:8]:
        who = "Customer" if turn.get("direction") == "inbound" else "Support"
        ch = (turn.get("channel") or "?").upper()
        text = (turn.get("text") or "")[:400]
        lines.append(f"  [{ch} · {who}]: {text}")
    return "\n".join(lines)


def _mask_fragments(fragments: list[str], known_values: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """Mask several text fragments in one mask_text() call (shared placeholder numbering),
    then split back apart. Falls back to the original fragments (no masking) if anything
    about the join/split round-trip goes wrong — e.g. a fragment containing the separator
    byte itself — so a masking edge case can never break answer generation.
    """
    try:
        combined = _PII_JOIN.join(fragments)
        masked_combined, mapping = mask_text(combined, known_values)
        parts = masked_combined.split(_PII_JOIN)
        if len(parts) != len(fragments):
            raise ValueError("fragment count mismatch after masking")
        return parts, mapping
    except Exception:
        return fragments, {}


def _known_values(graph_ctx: dict | None) -> dict[str, str]:
    """Extract the resolved customer's own name/phone/email for PII masking.

    Sourced from the same Neo4j graph_context dict already used elsewhere in this file —
    no new lookup. Missing fields are simply omitted (mask_text handles that).
    """
    if not graph_ctx:
        return {}
    return {
        "name": graph_ctx.get("name") or "",
        "phone": graph_ctx.get("phone") or "",
        "email": graph_ctx.get("email") or "",
    }


def _safe_amount(value) -> str:
    """Convert a currency value (int, float, or string) to a formatted rupee string."""
    try:
        return f"Rs.{int(float(str(value).replace(',', ''))):,}"
    except (ValueError, TypeError):
        return str(value) if value else "N/A"


def _format_graph_context(graph_ctx: dict | None) -> str:
    """Convert the Neo4j graph context dict into a clean human-readable string."""
    if not graph_ctx:
        return ""
    lines = []
    if graph_ctx.get("customer_id"):
        lines.append(f"Customer ID: {graph_ctx['customer_id']}")
    # Name is included (and PII-masked to [NAME_1] before this text reaches the LLM, then
    # restored in the final answer — see generate_answer()/_mask_fragments()) purely so
    # the LLM can address the customer by name. Phone/email are deliberately NOT included
    # here — they add no value to answer generation, so there's no reason to expose them.
    if graph_ctx.get("name"):
        lines.append(f"Customer Name: {graph_ctx['name']}")
    if graph_ctx.get("city"):
        lines.append(f"City: {graph_ctx['city']}")
    loans = graph_ctx.get("loans") or []
    if loans:
        lines.append("Loans:")
        for loan in loans:
            lines.append(
                f"  - {loan.get('loan_type', 'Loan')} (ID: {loan.get('loan_id', '')}) | "
                f"Status: {loan.get('status', '')} | "
                f"Amount: {_safe_amount(loan.get('amount_inr', 0))} | "
                f"Next step: {loan.get('next_step', '')}"
            )
    claims = graph_ctx.get("claims") or []
    if claims:
        lines.append("Claims:")
        for claim in claims:
            lines.append(
                f"  - {claim.get('policy_type', '')} / {claim.get('claim_type', '')} "
                f"(ID: {claim.get('claim_id', '')}) | "
                f"Status: {claim.get('status', '')} | "
                f"Claimed: {_safe_amount(claim.get('amount_claimed', 0))}"
            )
    policies = graph_ctx.get("policies") or []
    if policies:
        lines.append("Policies:")
        for p in policies:
            maturity = f" | Maturity: {p['maturity_date']}" if p.get("maturity_date") else ""
            next_due = f" | Next premium due: {p['next_premium_due']}" if p.get("next_premium_due") else ""
            lines.append(
                f"  - {p.get('policy_type', 'Policy')} (ID: {p.get('policy_id', '')}) | "
                f"Status: {p.get('status', '')} | "
                f"Coverage: {_safe_amount(p.get('coverage_inr', 0))} | "
                f"Premium: {_safe_amount(p.get('premium_inr', 0))}"
                f"{maturity}{next_due}"
            )
    return "\n".join(lines)
