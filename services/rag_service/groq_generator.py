import json
import os
from pathlib import Path


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
loan_status              – Customer asking about the status of an existing loan.
loan_application         – Customer wants to apply for a NEW loan (not check an existing one).
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
  → intent: loan_status  (checking existing application), secondary_intent: null

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

        sources = "\n\n".join(
            f"[{i}] {item.get('metadata', {}).get('source', 'unknown')}:\n{item['text']}"
            for i, item in enumerate(contexts, start=1)
        )
        graph_ctx_text = _format_graph_context(ctx.get("graph_context"))

        user_prompt = (
            f"{channel_rule}{lang_rule}\n\n"
            "Rules:\n"
            "- Answer ONLY using the retrieved context below. Do NOT invent facts.\n"
            "- Cite sources inline like [1] or [2]. List them at the end.\n"
            "- If the customer context includes open tickets, reference them by ticket ID and status.\n"
            "- If context is insufficient, say: \"I need to escalate this to our support team.\"\n"
            "- Never mention internal system names like OpenSearch, Neo4j, or RAG.\n\n"
            + (f"Customer account context:\n{graph_ctx_text}\n\n" if graph_ctx_text else "")
            + f"Customer query: {query}\n\n"
            f"Retrieved context:\n{sources or '(none)'}\n\n"
            "Answer:"
        )
        return self._generate(system_prompt=_system_prompt(), user_prompt=user_prompt)

    def classify_message(self, message: str, context: dict | None = None) -> dict | None:
        graph_ctx = context.get("graph_context") if context else None
        graph_text = _format_graph_context(graph_ctx) if graph_ctx else ""

        user_prompt = (
            "## Intent Definitions\n"
            f"{_INTENT_DEFINITIONS}\n\n"
            "## Few-Shot Examples\n"
            f"{_FEW_SHOT_EXAMPLES}\n\n"
            "## Classification Task\n"
            "Think step by step:\n"
            "1. Detect the customer's language. Set `language` to ISO-639-1 code (e.g. `en`, `hi`, `ta`).\n"
            "2. Identify key entities (product, action, emotion) in the message.\n"
            "3. Match to the PRIMARY intent from the list of 16 intents above.\n"
            "4. If the message contains a SECOND distinct request, set `secondary_intent`; otherwise set it to null.\n"
            "5. Determine urgency: high if fraud/stolen/urgent/ASAP/blocked/overdue; "
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
            + f"Customer message: {message}"
        )

        result = self._generate(
            system_prompt="You are a BFSI intent classifier. Return ONLY valid JSON. Never explain or add markdown.",
            user_prompt=user_prompt,
        )
        if not result["llm_used"]:
            return None
        try:
            text = result["text"].strip()
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

    def _generate(self, system_prompt: str, user_prompt: str) -> dict:
        if not self.api_key:
            return {"text": "", "model": self.model, "llm_used": False, "error": "GROQ_API_KEY not set"}
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
            return {"text": response.choices[0].message.content.strip(), "model": self.model, "llm_used": True}
        except Exception as exc:
            return {"text": "", "model": self.model, "llm_used": False, "error": str(exc)}


# ── Module-level helpers ──────────────────────────────────────────────────────

def _channel_format_rule(channel: str) -> str:
    if channel == "whatsapp":
        return "Format: Reply in 2–3 short sentences. Use bullet points only when listing 3+ items. Be conversational."
    if channel == "email":
        return "Format: Use structured paragraphs with a brief greeting and a professional closing. Be formal."
    return "Format: Be concise and professional."


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
    return "\n".join(lines)
