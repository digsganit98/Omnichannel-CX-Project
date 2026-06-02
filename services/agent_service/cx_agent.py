from pydantic import ValidationError

from services.intent_service.classifier import classify_intent
from services.intent_service.sentiment import detect_sentiment
from services.intent_service.urgency import detect_urgency
from services.rag_service.generator import OllamaGenerator
from shared.schemas.intents import IntentResult, Urgency


URGENCY_RANK = {
    Urgency.LOW: 0,
    Urgency.MEDIUM: 1,
    Urgency.HIGH: 2,
}


class CXAgent:
    def __init__(self, generator: OllamaGenerator | None = None) -> None:
        self.generator = generator or OllamaGenerator()

    def analyze(self, message: str, context: dict | None = None) -> IntentResult:
        llm_result = self.generator.classify_message(message, context or {})
        if llm_result:
            try:
                values = {
                    **llm_result,
                    "analysis_source": "ollama_llm",
                    "reason": llm_result.get("reason") or llm_result.get("rationale") or "Classified by local LLM.",
                }
                return self._apply_guardrails(message, IntentResult(**values))
            except ValidationError:
                pass
        return classify_intent(message)

    @staticmethod
    def _apply_guardrails(message: str, result: IntentResult) -> IntentResult:
        guarded_fields = []
        rule_sentiment = detect_sentiment(message)
        if rule_sentiment == "negative" and result.sentiment != "negative":
            result.sentiment = "negative"
            guarded_fields.append("sentiment")
        elif result.sentiment not in {"negative", "neutral", "positive"}:
            result.sentiment = rule_sentiment
            guarded_fields.append("sentiment")

        rule_urgency = Urgency(detect_urgency(message, result.sentiment))
        if URGENCY_RANK[rule_urgency] > URGENCY_RANK[result.urgency]:
            result.urgency = rule_urgency
            guarded_fields.append("urgency")

        if guarded_fields:
            result.reason += f" Deterministic guardrails raised: {', '.join(guarded_fields)}."
        return result
