import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from services.rag_service.config import ollama_base_url, ollama_enabled, ollama_model, ollama_timeout_seconds


class OllamaGenerator:
    def __init__(self) -> None:
        self.base_url = ollama_base_url().rstrip("/")
        self.model = ollama_model()
        self.enabled = ollama_enabled()
        self.timeout = ollama_timeout_seconds()

    def generate_answer(self, query: str, contexts: list[dict], conversation_context: dict | None = None) -> dict:
        sources = "\n\n".join(
            f"[{index}] {item.get('metadata', {}).get('source', 'unknown')}: {item['text']}"
            for index, item in enumerate(contexts, start=1)
        )
        prompt = (
            "Answer the customer using only the retrieved context. Include citations like [1]. "
            "If context is insufficient, say manual review is required. Do not invent order status.\n\n"
            f"Conversation context: {json.dumps(conversation_context or {}, default=str)}\n\n"
            f"Customer query: {query}\n\nRetrieved context:\n{sources}\n\nAnswer:"
        )
        return self._generate(prompt)

    def classify_message(self, message: str, context: dict | None = None) -> dict | None:
        prompt = (
            "Classify the customer message. Return only JSON with intent, confidence, urgency, sentiment, reason. "
            "Allowed intents: order_tracking, refund_request, return_request, product_information, billing_issue, "
            "technical_support, complaint, general_inquiry, human_escalation. Allowed urgency: low, medium, high. "
            "Treat words such as immediately, urgent, ASAP, critical, or escalate as high urgency. "
            "Treat cancellation, refund problems, complaints, and requests for a human during a problem as negative sentiment. "
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
        status = {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "model": self.model,
            "timeout_seconds": self.timeout,
            "reachable": None,
            "model_installed": None,
        }
        if not check_connection or not self.enabled:
            return status
        request = Request(f"{self.base_url}/api/tags", method="GET")
        try:
            with urlopen(request, timeout=min(self.timeout, 5)) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = [item.get("name", "") for item in payload.get("models", [])]
            status["reachable"] = True
            status["model_installed"] = self.model in models
            status["available_models"] = models
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            status["reachable"] = False
            status["error"] = str(exc)
        return status

    def _generate(self, prompt: str) -> dict:
        if not self.enabled:
            return {"text": "", "model": self.model, "llm_used": False, "error": "OLLAMA_ENABLED=false"}
        request = Request(
            f"{self.base_url}/api/generate",
            method="POST",
            data=json.dumps({"model": self.model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return {"text": payload.get("response", "").strip(), "model": self.model, "llm_used": True}
        except (URLError, TimeoutError, OSError) as exc:
            return {"text": "", "model": self.model, "llm_used": False, "error": str(exc)}
