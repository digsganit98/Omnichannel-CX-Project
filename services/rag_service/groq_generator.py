import json
import os

import groq as groq_sdk


class GroqGenerator:
    def __init__(self) -> None:
        self.api_key = os.getenv("GROQ_API_KEY", "")
        self.model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        self.timeout = int(os.getenv("GROQ_TIMEOUT_SECONDS", "30"))
        self._client: groq_sdk.Groq | None = None

    @property
    def _groq(self) -> groq_sdk.Groq:
        if self._client is None:
            self._client = groq_sdk.Groq(api_key=self.api_key)
        return self._client

    def generate_answer(self, query: str, contexts: list[dict], conversation_context: dict | None = None) -> dict:
        sources = "\n\n".join(
            f"[{index}] {item.get('metadata', {}).get('source', 'unknown')}: {item['text']}"
            for index, item in enumerate(contexts, start=1)
        )
        prompt = (
            "You are a BFSI customer support AI. Answer the customer using only the retrieved context. "
            "Include citations like [1]. If context is insufficient, say manual review is required. "
            "Do not invent account balances, loan amounts, or policy details.\n\n"
            f"Conversation context: {json.dumps(conversation_context or {}, default=str)}\n\n"
            f"Customer query: {query}\n\nRetrieved context:\n{sources}\n\nAnswer:"
        )
        return self._generate(prompt)

    def classify_message(self, message: str, context: dict | None = None) -> dict | None:
        prompt = (
            "Classify the BFSI customer message. Return only valid JSON with keys: "
            "intent, confidence, urgency, sentiment, reason. "
            "Allowed intents: account_balance_inquiry, transaction_dispute, fund_transfer, loan_status, "
            "loan_application, loan_default_notice, policy_status, insurance_claim, card_management, "
            "kyc_update, fraud_report, complaint, general_inquiry, human_escalation. "
            "Allowed urgency: low, medium, high. "
            "Treat fraud, stolen, hacked, blocked, overdue, immediately, urgent, ASAP as high urgency. "
            "Treat fraud reports, unauthorized transactions, stolen money as negative sentiment. "
            f"Context: {json.dumps(context or {}, default=str)} Message: {message}"
        )
        result = self._generate(prompt)
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

    def _generate(self, prompt: str) -> dict:
        if not self.api_key:
            return {"text": "", "model": self.model, "llm_used": False, "error": "GROQ_API_KEY not set"}
        try:
            response = self._groq.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                timeout=self.timeout,
            )
            return {"text": response.choices[0].message.content.strip(), "model": self.model, "llm_used": True}
        except Exception as exc:
            return {"text": "", "model": self.model, "llm_used": False, "error": str(exc)}
