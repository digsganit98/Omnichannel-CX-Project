from pydantic import ValidationError

from services.intent_service.classifier import classify_intent
from services.intent_service.sentiment import detect_sentiment
from services.intent_service.urgency import detect_urgency
from services.rag_service.groq_generator import GroqGenerator
from shared.schemas.intents import Intent, IntentResult, Urgency


URGENCY_RANK = {
    Urgency.LOW: 0,
    Urgency.MEDIUM: 1,
    Urgency.HIGH: 2,
}


class CXAgent:
    def __init__(self, generator: GroqGenerator | None = None) -> None:
        self.generator = generator or GroqGenerator()

    def analyze(self, message: str, context: dict | None = None) -> IntentResult:
        llm_result = self.generator.classify_message(message, context or {})
        if llm_result:
            try:
                # Map secondary_intent string to Intent enum safely
                secondary_raw = llm_result.get("secondary_intent")
                secondary = None
                if secondary_raw and secondary_raw != "null":
                    try:
                        from shared.schemas.intents import Intent as _Intent
                        secondary = _Intent(secondary_raw)
                    except ValueError:
                        secondary = None

                values = {
                    **llm_result,
                    "secondary_intent": secondary,
                    "language": llm_result.get("language", "en") or "en",
                    "analysis_source": "groq_llm",
                    "reason": llm_result.get("reason") or llm_result.get("rationale") or "Classified by Groq LLM.",
                }
                return self._apply_guardrails(message, IntentResult(**values))
            except ValidationError:
                pass
        return classify_intent(message)

    @staticmethod
    def _apply_guardrails(message: str, result: IntentResult) -> IntentResult:
        guarded_fields = []
        rule_result = classify_intent(message)
        boundary_intents = {
            Intent.LOAN_STATUS,
            Intent.LOAN_APPLICATION,
            Intent.CLAIM_STATUS,
            Intent.INSURANCE_CLAIM,
            Intent.HUMAN_ESCALATION,
        }
        # Only override LLM intent with rule result when the LLM is uncertain (< 0.65)
        # AND the rule classifier is confident (> 0.70). A high-confidence LLM result for
        # "I applied 3 weeks ago, any update?" should not be overwritten by keyword matching.
        if (
            rule_result.intent in boundary_intents
            and result.intent != rule_result.intent
            and result.confidence < 0.65
            and rule_result.confidence > 0.70
        ):
            result.intent = rule_result.intent
            guarded_fields.append("intent")

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
