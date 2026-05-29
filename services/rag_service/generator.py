import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from langchain_core.prompts import PromptTemplate

from services.rag_service.config import ollama_base_url, ollama_model


RAG_PROMPT = PromptTemplate.from_template(
    """You are a GenAI customer experience assistant for an e-commerce support team.

Use only the retrieved context to answer the customer. If the context is insufficient,
say that a support ticket should be created. Be concise, empathetic, and operational.
Do not mention brands, platforms, policies, timelines, or facts that are not present in
the retrieved context. Do not invent order status.

Customer query:
{query}

Retrieved context:
{context}

Answer:"""
)


CLASSIFICATION_PROMPT = PromptTemplate.from_template(
    """Classify this e-commerce customer message.

Return only valid JSON with these keys:
intent, sentiment, urgency, rationale

Allowed intents: order_tracking, refund_request, billing_issue, technical_support, general_question
Allowed sentiment: positive, neutral, negative
Allowed urgency: low, medium, high

Message:
{message}
"""
)


class OllamaGenerator:
    def __init__(self) -> None:
        self.base_url = ollama_base_url().rstrip("/")
        self.model = ollama_model()

    def generate_answer(self, query: str, contexts: list[dict]) -> dict:
        context_text = "\n\n---\n\n".join(item["text"] for item in contexts)
        prompt = RAG_PROMPT.format(query=query, context=context_text)
        return self._generate(prompt)

    def classify_message(self, message: str) -> dict | None:
        prompt = CLASSIFICATION_PROMPT.format(message=message)
        result = self._generate(prompt)
        if not result["llm_used"]:
            return None
        try:
            text = result["text"].strip()
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end >= start:
                return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return None

    def _generate(self, prompt: str) -> dict:
        request = Request(
            f"{self.base_url}/api/generate",
            method="POST",
            data=json.dumps(
                {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return {
                    "text": payload.get("response", "").strip(),
                    "model": self.model,
                    "llm_used": True,
                }
        except (URLError, TimeoutError, OSError) as exc:
            return {
                "text": "",
                "model": self.model,
                "llm_used": False,
                "error": str(exc),
            }
