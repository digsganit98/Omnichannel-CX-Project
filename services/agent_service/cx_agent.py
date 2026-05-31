from pydantic import ValidationError

from services.intent_service.classifier import classify_intent
from services.rag_service.generator import OllamaGenerator
from shared.schemas.intents import IntentResult


class CXAgent:
    def __init__(self, generator: OllamaGenerator | None = None) -> None:
        self.generator = generator or OllamaGenerator()

    def analyze(self, message: str, context: dict | None = None) -> IntentResult:
        llm_result = self.generator.classify_message(message, context or {})
        if llm_result:
            try:
                return IntentResult(
                    **llm_result,
                    analysis_source="ollama_llm",
                    reason=llm_result.get("reason") or llm_result.get("rationale") or "Classified by local LLM.",
                )
            except ValidationError:
                pass
        return classify_intent(message)
