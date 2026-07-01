import json
import logging
import os
import re
from functools import lru_cache
from typing import Any

from services.rag_service.groq_generator import GroqGenerator
from services.resolution_service.prompts import build_resolution_prompt

logger = logging.getLogger(__name__)

ALLOWED_LEVELS = {"L1", "L2", "L3"}
GROQ_PLACEHOLDERS = {"", "groq_api_key_here", "xxxxx", "replace-with-groq-api-key"}
BREAKDOWN_KEYS = (
    "query_clarity",
    "intent_alignment",
    "sentiment_alignment",
    "severity",
    "business_risk",
    "ambiguity",
    "level_consistency",
)

L3_SIGNALS = {
    "fraud",
    "hacked",
    "hack",
    "unauthorized",
    "not authorized",
    "without my permission",
    "without authorization",
    "phishing",
    "otp",
    "scam",
    "stolen",
    "identity theft",
    "sim swap",
    "forged",
    "forgery",
    "legal complaint",
    "ombudsman",
    "regulator",
    "rbi",
    "data leak",
    "leaked",
    "account takeover",
    "unknown transactions",
    "beneficiary without",
}

L2_SIGNALS = {
    "failed but money was deducted",
    "money was deducted",
    "deducted twice",
    "not delivered",
    "not received",
    "pending",
    "not credited",
    "incorrect",
    "wrong",
    "status",
    "delay",
    "delayed",
    "still under review",
    "not reflected",
    "not processed",
    "complaint",
    "refund",
    "charge",
    "blocked",
    "increase limit",
    "emi",
    "claim rejected",
}

L2_STATUS_OR_FAILURE_SIGNALS = {
    "status",
    "delay",
    "delayed",
    "pending",
    "not approved",
    "not processed",
    "not reflected",
    "not credited",
    "rejected",
    "failed",
    "deducted",
    "missing",
    "incorrect",
    "wrong",
}

L1_PATTERNS = (
    "how do i",
    "how can i",
    "can i",
    "can i apply",
    "am i eligible",
    "is it possible",
    "what is the process",
    "what is",
    "what are",
    "where is",
    "documents required",
    "eligibility",
    "process",
    "timings",
    "charges",
    "difference between",
)


class ResolutionDecisionEngine:
    """Prompt-only BFSI L1/L2/L3 resolution classifier."""

    def __init__(
        self,
        generator: Any | None = None,
        fallback_generator: Any | None = None,
        **_: Any,
    ) -> None:
        self.generator = generator or GroqGenerator()
        self.fallback_generator = fallback_generator or self._try_ollama_generator()

    def resolve_query_level(self, query: str, intent: str, sentiment: str) -> dict[str, Any]:
        clean_query = (query or "").strip()
        clean_intent = str(intent or "unknown").strip()
        clean_sentiment = str(sentiment or "neutral").strip()

        if not clean_query:
            return self._safe_fallback_decision(clean_query, clean_intent, clean_sentiment, "Empty query received.")

        prompt = build_resolution_prompt(clean_query, clean_intent, clean_sentiment)
        llm_result = self._call_llm(prompt)

        if llm_result.get("llm_used") and llm_result.get("text"):
            parsed = self._parse_llm_json(llm_result["text"], clean_intent, clean_sentiment)
            if parsed:
                return parsed
            logger.warning("resolution_llm_json_parse_failed", extra={"text": llm_result.get("text", "")[:500]})

        reason = llm_result.get("error") or "LLM did not return a usable decision."
        return self._safe_fallback_decision(clean_query, clean_intent, clean_sentiment, reason)

    def _call_llm(self, prompt: str) -> dict[str, Any]:
        try:
            if isinstance(self.generator, GroqGenerator):
                if os.getenv("GROQ_API_KEY", "").strip() in GROQ_PLACEHOLDERS:
                    return {"text": "", "llm_used": False, "error": "GROQ_API_KEY is not configured."}
                result = self.generator._generate(
                    system_prompt="You are a BFSI resolution classifier. Return ONLY valid JSON.",
                    user_prompt=prompt,
                )
            elif self.generator.__class__.__name__ == "OllamaGenerator":
                result = self.generator._generate(prompt)
            elif hasattr(self.generator, "_generate"):
                result = self.generator._generate(prompt)
            else:
                result = {"text": "", "llm_used": False, "error": "Unsupported generator interface."}
            if result.get("llm_used"):
                return result
        except Exception as exc:
            logger.warning("resolution_primary_llm_failed", extra={"error": str(exc)})

        if self.fallback_generator is None:
            return {"text": "", "llm_used": False, "error": "No fallback LLM generator configured."}
        try:
            return self.fallback_generator._generate(prompt)
        except Exception as exc:
            return {"text": "", "llm_used": False, "error": str(exc)}

    @staticmethod
    def _try_ollama_generator() -> Any | None:
        try:
            from services.rag_service.generator import OllamaGenerator

            return OllamaGenerator()
        except Exception:
            return None

    def _parse_llm_json(self, text: str, intent: str, sentiment: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(self._extract_json_object(text))
        except (json.JSONDecodeError, ValueError, TypeError):
            return None
        if not isinstance(payload, dict):
            return None

        level = str(payload.get("resolution_level", "")).strip().upper()
        if level not in ALLOWED_LEVELS:
            return None

        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        return {
            "intent": str(payload.get("intent") or intent),
            "sentiment": str(payload.get("sentiment") or sentiment),
            "resolution_level": level,
            "confidence": max(0.0, min(1.0, confidence)),
            "confidence_breakdown": self._normalise_breakdown(payload.get("confidence_breakdown")),
            "reason": str(payload.get("reason") or "Resolution level selected from prompt rules.").strip(),
        }

    @staticmethod
    def _normalise_breakdown(value: Any) -> dict[str, float]:
        raw = value if isinstance(value, dict) else {}
        breakdown: dict[str, float] = {}
        for key in BREAKDOWN_KEYS:
            try:
                score = float(raw.get(key, 0.0))
            except (TypeError, ValueError):
                score = 0.0
            breakdown[key] = max(0.0, min(1.0, score))
        return breakdown

    @staticmethod
    def _fallback_breakdown(level: str) -> dict[str, float]:
        if level == "L1":
            return {
                "query_clarity": 0.70,
                "intent_alignment": 0.55,
                "sentiment_alignment": 0.65,
                "severity": 0.20,
                "business_risk": 0.20,
                "ambiguity": 0.35,
                "level_consistency": 0.62,
            }
        if level == "L3":
            return {
                "query_clarity": 0.75,
                "intent_alignment": 0.70,
                "sentiment_alignment": 0.80,
                "severity": 0.90,
                "business_risk": 0.95,
                "ambiguity": 0.25,
                "level_consistency": 0.82,
            }
        if level == "L2":
            return {
                "query_clarity": 0.68,
                "intent_alignment": 0.62,
                "sentiment_alignment": 0.62,
                "severity": 0.58,
                "business_risk": 0.60,
                "ambiguity": 0.38,
                "level_consistency": 0.68,
            }
        return {
            "query_clarity": 0.30,
            "intent_alignment": 0.25,
            "sentiment_alignment": 0.30,
            "severity": 0.40,
            "business_risk": 0.45,
            "ambiguity": 0.80,
            "level_consistency": 0.30,
        }

    @staticmethod
    def _safe_fallback_decision(query: str, intent: str, sentiment: str, reason: str) -> dict[str, Any]:
        text = f"{query} {intent}".lower()
        if any(signal in text for signal in L3_SIGNALS):
            return {
                "intent": intent,
                "sentiment": sentiment,
                "resolution_level": "L3",
                "confidence": 0.74,
                "confidence_breakdown": ResolutionDecisionEngine._fallback_breakdown("L3"),
                "reason": f"LLM unavailable; safety fallback detected critical BFSI risk. {reason}".strip(),
            }
        if (
            any(pattern in text for pattern in L1_PATTERNS)
            and not any(signal in text for signal in L2_STATUS_OR_FAILURE_SIGNALS)
        ):
            return {
                "intent": intent,
                "sentiment": sentiment,
                "resolution_level": "L1",
                "confidence": 0.58,
                "confidence_breakdown": ResolutionDecisionEngine._fallback_breakdown("L1"),
                "reason": f"LLM unavailable; safety fallback detected a general informational query. {reason}".strip(),
            }
        if any(signal in text for signal in L2_SIGNALS):
            return {
                "intent": intent,
                "sentiment": sentiment,
                "resolution_level": "L2",
                "confidence": 0.62,
                "confidence_breakdown": ResolutionDecisionEngine._fallback_breakdown("L2"),
                "reason": f"LLM unavailable; safety fallback detected a verification-required issue. {reason}".strip(),
            }
        return {
            "intent": intent,
            "sentiment": sentiment,
            "resolution_level": "L2",
            "confidence": 0.35,
            "confidence_breakdown": ResolutionDecisionEngine._fallback_breakdown("unknown"),
            "reason": f"Prompt-only classifier unavailable; routed to assisted review. {reason}".strip(),
        }

    @staticmethod
    def _extract_json_object(text: str) -> str:
        match = re.search(r"\{.*\}", text.strip(), flags=re.DOTALL)
        if not match:
            raise ValueError("No JSON object found.")
        return match.group(0)


@lru_cache(maxsize=1)
def _default_engine() -> ResolutionDecisionEngine:
    return ResolutionDecisionEngine()


def resolve_query_level(query: str, intent: str, sentiment: str) -> dict[str, Any]:
    """Public orchestration entrypoint for L1/L2/L3 resolution routing."""
    return _default_engine().resolve_query_level(query, intent, sentiment)
