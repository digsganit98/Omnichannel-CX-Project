from services.intent_service.classifier import classify_intent
from services.intent_service.sentiment import detect_sentiment
from services.intent_service.urgency import detect_urgency
from services.rag_service.generator import OllamaGenerator


class CXAgent:
    def __init__(self) -> None:
        self.generator = OllamaGenerator()

    def analyze(self, message: str) -> dict:
        llm_result = self.generator.classify_message(message)
        if llm_result:
            intent = llm_result.get("intent") or "general_question"
            sentiment = llm_result.get("sentiment") or "neutral"
            urgency = llm_result.get("urgency") or "low"
            return {
                "intent": intent,
                "sentiment": sentiment,
                "urgency": urgency,
                "analysis_source": "ollama_llm",
                "rationale": llm_result.get("rationale"),
            }

        intent = classify_intent(message)
        sentiment = detect_sentiment(message)
        urgency = detect_urgency(message, sentiment)
        return {
            "intent": intent,
            "sentiment": sentiment,
            "urgency": urgency,
            "analysis_source": "rule_fallback",
            "rationale": "Local LLM was unavailable or returned invalid JSON.",
        }
