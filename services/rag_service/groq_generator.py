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
account_balance_inquiry  – Customer wants to know their account balance or recent transactions. ALSO use this for FIXED DEPOSIT (FD) questions — maturity date, maturity amount, principal, interest rate or tenure — since fixed deposits are held on the customer's account records.
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
            "- If you cannot fully answer from the data below, give what you can and then say a "
            "support specialist can help further with the rest. Do NOT promise that you are "
            "escalating, raising, or logging anything — the system decides separately whether a "
            "ticket is created, so never state or imply that an escalation/ticket has happened.\n"
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

    def summarize_case(self, turns: list[dict], context: dict | None = None) -> dict | None:
        """An agent-facing summary of where this conversation stands.

        Written for a human picking up a conversation cold, not for the model: the
        pipeline already feeds recent turns and open cases into every reply. Returns
        None when the LLM is unavailable so the caller can fall back rather than
        display a fabricated summary.

        Deliberately NOT called per message. A summary is only worth generating when
        an agent actually opens the conversation, so the route caches it against the
        latest turn id — cost tracks agent attention, not message volume.
        """
        ctx = context or {}
        if not turns:
            return None

        history_text = _format_conversation_history(turns)
        cases = ctx.get("open_cases") or []
        cases_text = ""
        if cases:
            lines = ["Open support cases on record:"]
            for case in cases[:5]:
                lines.append(
                    f"  - {case.get('ticket_id', '?')} | {case.get('title') or case.get('intent') or 'case'}"
                    f" | scope {case.get('ticket_scope') or '-'} | {case.get('status') or 'open'}"
                )
            cases_text = "\n".join(lines)

        known_values = _known_values(ctx.get("graph_context"))
        (history_text, cases_text), pii_mapping = _mask_fragments(
            [history_text, cases_text], known_values
        )

        user_prompt = (
            "Summarise this support conversation for the agent taking it over.\n\n"
            "Return ONLY a JSON object with exactly these keys:\n"
            '{"situation": "<what the customer is dealing with, 1-2 sentences>", '
            '"open_items": ["<each unresolved item, one short line>"]}\n\n'
            "Rules:\n"
            "- Use ONLY what appears below. Never infer an outcome, a promise or a date that is not stated.\n"
            "- If the customer raised several separate matters, give each its own line in open_items.\n"
            # The history can contain our own earlier status emails, which quote a ticket
            # list that was true when sent and is stale now. Those are message TEXT, not
            # records: the open cases block above is the system of record, and a ticket
            # resolved since that email must not reappear because a message still names it.
            "- open_items must list ONLY the cases in the 'Open support cases on record' "
            "block above. A ticket id mentioned in the messages but absent from that block "
            "is CLOSED - never list it. If that block is absent, open_items is [].\n"
            "- Do not copy status wording out of the messages (assignments, expected "
            "resolution times). Describe a case from the record, not from what an earlier "
            "reply said about it.\n"
            "- Name amounts and reference ids where they appear, so the agent can act without scrolling.\n"
            # Situation and open_items otherwise repeat the same ticket id and amount,
            # which is most of the card's width in a narrow panel.
            "- Name each ticket id ONCE, in open_items. Do not repeat it in situation, and "
            "do not restate an open item inside situation.\n"
            "- open_items is [] when nothing is outstanding.\n"
            # Half the outbound turns in a held conversation are the automatic
            # "Support Agent will help you shortly" placeholder, so describing the latest
            # exchange means describing that placeholder unless it is excluded.
            "- Ignore automatic holding messages such as 'Support Agent will help you "
            "with this shortly' - they are not part of the case.\n"
            "- Plain ASCII punctuation only: ordinary spaces, hyphens and apostrophes.\n"
            "- No markdown, no preamble.\n\n"
            + (f"{cases_text}\n\n" if cases_text else "")
            + history_text
        )

        result = self._generate(
            system_prompt=(
                "You summarise customer support conversations for the human agent taking over. "
                "Return ONLY valid JSON. Never explain or add markdown."
            ),
            user_prompt=user_prompt,
            operation="case_summary",
            metadata={"turns": len(turns), "open_cases": len(cases)},
        )
        if not result["llm_used"]:
            return None
        try:
            text = unmask_text(result["text"].strip(), pii_mapping)
            parsed = json.loads(text[text.find("{") : text.rfind("}") + 1])
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(parsed, dict):
            return None
        items = parsed.get("open_items")
        return {
            "situation": _clean_summary_text(parsed.get("situation")),
            # A model can return a bare string here; normalise so the UI never has to guess.
            "open_items": [_clean_summary_text(i) for i in items if _clean_summary_text(i)]
            if isinstance(items, list)
            else ([_clean_summary_text(items)] if items else []),
            "model": result.get("model"),
        }

    def categorize_customer_record(self, record_text: str) -> dict | None:
        """Sort a customer's record fields into the five Customer Context tabs.

        Returns ``{"categories": {...}, "model": ...}`` on success, or
        ``{"raw": "<model text>", "model": ...}`` when the response could not be parsed
        as the agreed shape — the caller shows the raw text rather than losing content
        to a failed guess. ``None`` only when the LLM itself was unavailable.

        The contract is label/value PAIRS, never formatted strings: asking a model for
        "a readable list" gets a different format on every run (commas, dashes, newlines,
        nothing) and needs a fragile parser to undo. Structure removes that at the source,
        and json_mode makes the provider return a document rather than prose around one.
        """
        if not record_text.strip():
            return None

        user_prompt = (
            "Sort every field below into exactly these five categories.\n\n"
            "Return ONLY a JSON object with exactly these five keys:\n"
            '{"profile": [{"label": "...", "value": "..."}], '
            '"holdings": [], "activity": [], "claims": [], "risk": []}\n\n'
            "Rules:\n"
            "- EVERY key must be present. Use [] for a category with no fields.\n"
            '- Each item is {"label": "...", "value": "..."} with an optional short '
            '"sub". Never a bare string, never nested objects.\n'
            # A field name is not context. Left unsaid, the model uses sub as a
            # provenance label ("dpd", "penalty_details") and spends a whole row on it.
            '- "sub" is ONLY for a reference id, a date or a status the agent needs '
            '(e.g. "TXN0001000003 - pending"). NEVER the source field\'s name, and never '
            "a restatement of the label or value. Omit it when there is nothing to add.\n"
            '- "label" NAMES the thing (what an agent scans down the left). "value" is '
            "what it IS. Never put an identifier in value and its description in label - "
            '"Debit IMPS 5776.55"/"TXN0001000003" is backwards; write '
            '"IMPS to Samarth Thaker"/"Rs.5776.55" with sub "TXN0001000003 - pending".\n'
            '- "value" carries the value EXACTLY as given - never round, reformat or '
            "invent one.\n"
            "- Omit any field whose value is empty, zero, 'N/A' or 'None'.\n"
            '- "risk" holds only fields signalling a problem: days past due, fraud or '
            "chargeback flags, balance below minimum, penalties, stuck or failed "
            "payments, rejected claims. Healthy fields stay in their own category.\n"
            # With one card, "Mastercard Classic - " on every row is ~20 wasted
            # characters in a narrow panel and tells the agent nothing.
            "- Keep labels SHORT (2-4 words). Prefix a label with its instrument ONLY "
            "when the customer holds two or more of that kind and the rows would "
            'otherwise be ambiguous. With a single card write "Credit limit", not '
            '"Mastercard Classic - Credit Limit".\n'
            # Short must not mean anonymous. Stripped to the channel alone, eight
            # transactions render as an unreadable column of "UPI", "IMPS", "UPI".
            "- For a transaction the label names WHO it was to, not just the channel: "
            '"IMPS to Samarth Thaker", never "IMPS" or a status like '
            '"Debited-Pending". For a claim, name the claim type.\n'
            # Without a ceiling the model itemises every field of every record and runs
            # past the token budget mid-document, which json_mode rejects outright.
            "- At most 8 items per category. Keep only what an agent would act on.\n"
            "- Plain ASCII only. No markdown, no preamble.\n\n"
            + record_text
        )

        result = self._generate(
            system_prompt=(
                "You organise a banking customer's records into fixed categories for a "
                "support agent's screen. Return ONLY valid JSON. Never explain, never "
                "use markdown."
            ),
            user_prompt=user_prompt,
            operation="customer_context",
            metadata={"record_chars": len(record_text)},
            json_mode=True,
            # Sized against two measured limits, not guessed:
            #  - json_mode rejects a TRUNCATED document outright (400 json_validate_
            #    failed, empty failed_generation) instead of returning partial text, so
            #    the ceiling must clear the whole document. Measured: 1,648 completion
            #    tokens for a customer with 14 records.
            #  - max_tokens is RESERVED against the 8000 tokens-per-minute cap on this
            #    tier, so an over-generous ceiling 413s on its own. 8192 made a ~1.2K
            #    prompt request total 9735 and failed.
            # 4000 clears the document with ~2x margin and leaves TPM room for the
            # pipeline's other calls in the same minute.
            max_tokens=4000,
        )
        if not result["llm_used"]:
            return None

        text = (result.get("text") or "").strip()
        try:
            parsed = json.loads(text[text.find("{") : text.rfind("}") + 1])
        except (json.JSONDecodeError, ValueError):
            return {"raw": text, "model": result.get("model")}
        if not isinstance(parsed, dict):
            return {"raw": text, "model": result.get("model")}
        return {"categories": parsed, "model": result.get("model")}

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
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> dict:
        # The sampling config that defines this call's "version" (see llm_usage._config_version).
        # Kept in one place so every record_llm_call below stamps the same version tag.
        call_params = {"temperature": 0.2}
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
                params=call_params,
            )
            return result
        started = time.perf_counter()
        # JSON mode makes the provider return a JSON document rather than prose that
        # happens to contain one. Opt-in: the older callers here scrape the braces out
        # of free text and must keep behaving exactly as they do today.
        extra: dict = {"response_format": {"type": "json_object"}} if json_mode else {}
        # A reasoning model spends completion tokens thinking BEFORE it emits output, so
        # a long structured answer can hit the provider's default ceiling mid-document.
        # In json_mode that returns a 400 (json_validate_failed) rather than a truncated
        # string, so callers producing long JSON must raise the ceiling explicitly.
        if max_tokens:
            extra["max_tokens"] = max_tokens
            call_params["max_tokens"] = max_tokens
        try:
            response = self._groq.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=call_params["temperature"],
                timeout=self.timeout,
                **extra,
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
                params=call_params,
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
                params=call_params,
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


def _clean_summary_text(value) -> str:
    """Fold the exotic whitespace and quotes the model emits into plain ASCII.

    Observed live: the model returned U+202F (narrow no-break space) inside a customer
    name, which renders as mojibake once the JSON is re-encoded. The source turns contain
    none of these characters - the model introduces them - so normalising on the way out
    is the right place, rather than trusting a prompt rule to prevent it.
    """
    text = str(value or "")
    for exotic, plain in (
        (" ", " "), (" ", " "), (" ", " "), (" ", " "),
        ("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'),
        ("‑", "-"), ("–", "-"), ("—", "-"),
    ):
        text = text.replace(exotic, plain)
    return " ".join(text.split()).strip()


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
    credit_cards = graph_ctx.get("credit_cards") or []
    if credit_cards:
        lines.append("Credit Cards:")
        for cc in credit_cards:
            lines.append(
                f"  - {cc.get('card_network', 'Card')} {cc.get('card_variant', '')} "
                f"(ID: {cc.get('card_id', '')}) | "
                f"Credit limit: {_safe_amount(cc.get('credit_limit', 0))} | "
                f"Balance due: {_safe_amount(cc.get('balance_due', 0))}"
            )
    accounts = graph_ctx.get("accounts") or []
    if accounts:
        lines.append("Accounts:")
        for a in accounts:
            lines.append(
                f"  - {a.get('account_type', 'Account')} {a.get('account_sub_type', '')} "
                f"(No: {a.get('account_number', '')}) | "
                f"Status: {a.get('status', '')} | "
                f"Avg monthly balance: {_safe_amount(a.get('avg_monthly_balance', 0))}"
            )
    fixed_deposits = graph_ctx.get("fixed_deposits") or []
    if fixed_deposits:
        lines.append("Fixed Deposits:")
        for fd in fixed_deposits:
            maturity = f" | Maturity: {fd['maturity_date']}" if fd.get("maturity_date") else ""
            lines.append(
                f"  - FD {fd.get('fd_id', '')} | "
                f"Principal: {_safe_amount(fd.get('principal_amount', 0))} | "
                f"Rate: {fd.get('interest_rate', 'N/A')}% | "
                f"Tenure: {fd.get('tenure_months', 'N/A')} months | "
                f"Status: {fd.get('status', '')}"
                f"{maturity}"
            )
    # Open support cases. Conversation history is a fixed recent-turns window, so a case
    # raised earlier scrolls out of view and the model stops knowing it exists even while
    # the ticket is still open. Listing it here makes it a durable fact about the customer,
    # like a card limit. Summary only (id/subject/status) — the case's messages are not
    # replayed, so this stays a handful of tokens.
    open_cases = graph_ctx.get("open_cases") or []
    if open_cases:
        lines.append("Open support cases (already raised — do NOT treat as new):")
        for case in open_cases:
            subject = case.get("title") or (case.get("intent") or "").replace("_", " ").title()
            scope = case.get("scope") or ""
            # "transaction_dispute:imps" → "imps": the specific matter, without repeating the intent.
            detail = f" about {scope.split(':', 1)[1]}" if ":" in scope and scope.split(":", 1)[1] else ""
            lines.append(
                f"  - {case.get('ticket_id', '')} | {subject}{detail} | "
                f"Status: {case.get('status', 'open')}"
            )
    return "\n".join(lines)
