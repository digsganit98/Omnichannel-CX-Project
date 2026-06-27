import json
import logging
import re
from collections import Counter
from functools import lru_cache
from typing import Any

from services.rag_service.groq_generator import GroqGenerator
from services.resolution_service.prompts import build_resolution_prompt
from services.resolution_service.resolution_loader import ResolutionExampleLoader

logger = logging.getLogger(__name__)

ALLOWED_LEVELS = {"L1", "L2", "L3"}
DEFAULT_TOP_K = 5


class ResolutionDecisionEngine:
    """Classifies BFSI support queries into L1/L2/L3 using examples, vectors, and LLM reasoning."""

    def __init__(
        self,
        store: Any | None = None,
        loader: ResolutionExampleLoader | None = None,
        generator: Any | None = None,
        fallback_generator: Any | None = None,
    ) -> None:
        self.store = store or self._create_vector_store()
        self.loader = loader or ResolutionExampleLoader()
        self.generator = generator or GroqGenerator()
        self.fallback_generator = fallback_generator or self._try_ollama_generator()

    def resolve_query_level(self, query: str, intent: str, sentiment: str) -> dict[str, Any]:
        clean_query = (query or "").strip()
        clean_intent = str(intent or "unknown").strip()
        clean_sentiment = str(sentiment or "neutral").strip()

        if not clean_query:
            return self._fallback_decision(clean_intent, clean_sentiment, [], "Empty query received.")

        examples = self.retrieve_similar_examples(clean_query, top_k=DEFAULT_TOP_K)
        prompt = build_resolution_prompt(clean_query, clean_intent, clean_sentiment, examples)
        llm_result = self._call_llm(prompt)

        if llm_result.get("llm_used") and llm_result.get("text"):
            parsed = self._parse_llm_json(llm_result["text"], clean_intent, clean_sentiment)
            if parsed:
                return parsed
            logger.warning("resolution_llm_json_parse_failed", extra={"text": llm_result.get("text", "")[:500]})

        reason = llm_result.get("error") or "LLM did not return a usable decision."
        return self._fallback_decision(clean_intent, clean_sentiment, examples, reason)

    def retrieve_similar_examples(self, query: str, top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
        try:
            self._ensure_examples_indexed()
            vector = self.store.embeddings.embed_query(query)
            response = self.store.client.search(
                index=self.store.index_name,
                body={
                    "size": top_k,
                    "query": {
                        "bool": {
                            "must": [{
                                "knn": {
                                    "embedding": {
                                        "vector": vector,
                                        "k": top_k,
                                    }
                                }
                            }],
                            "filter": [{"term": {"metadata.doc_type.keyword": "resolution_example"}}],
                        }
                    },
                    "_source": ["text", "metadata"],
                },
            )
            hits = response.get("hits", {}).get("hits", [])
            examples = [self._hit_to_example(hit) for hit in hits]
            if examples:
                return examples
        except Exception as exc:
            logger.warning("resolution_opensearch_retrieval_failed", extra={"error": str(exc)})

        return self._local_similarity_search(query, top_k)

    def _ensure_examples_indexed(self) -> None:
        documents = self.loader.load_documents()
        if not documents:
            return

        self.store.create_index(recreate=False)
        count = self.store.client.count(
            index=self.store.index_name,
            body={"query": {"term": {"metadata.doc_type.keyword": "resolution_example"}}},
        ).get("count", 0)
        if count >= len(documents):
            return
        self.store.index_documents(documents, recreate=False)

    def _hit_to_example(self, hit: dict[str, Any]) -> dict[str, Any]:
        metadata = hit.get("_source", {}).get("metadata", {})
        text = hit.get("_source", {}).get("text", "")
        return {
            "customer_query": self._extract_text_field(text, "Customer Query"),
            "intent": metadata.get("intent", ""),
            "resolution_level": metadata.get("resolution_level", ""),
            "reason": metadata.get("reason", "") or self._extract_text_field(text, "Reason"),
            "score": round(float(hit.get("_score", 0.0)), 4),
        }

    def _local_similarity_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        examples = self.loader.load_examples()
        if not examples:
            return []
        query_vector = self.store.embeddings.embed_query(query)
        example_vectors = self.store.embeddings.embed_documents([item.to_search_text() for item in examples])
        scored = sorted(
            zip(examples, example_vectors),
            key=lambda item: self._cosine(query_vector, item[1]),
            reverse=True,
        )[:top_k]
        return [
            {
                **example.to_prompt_dict(),
                "score": round(self._cosine(query_vector, vector), 4),
            }
            for example, vector in scored
        ]

    def _call_llm(self, prompt: str) -> dict[str, Any]:
        try:
            if isinstance(self.generator, GroqGenerator):
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

    @staticmethod
    def _create_vector_store() -> Any:
        from services.rag_service.opensearch_store import OpenSearchVectorStore

        return OpenSearchVectorStore()

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
            "reason": str(payload.get("reason") or "Resolution level selected by LLM.").strip(),
        }

    def _fallback_decision(
        self,
        intent: str,
        sentiment: str,
        examples: list[dict[str, Any]],
        reason: str,
    ) -> dict[str, Any]:
        levels = [str(item.get("resolution_level", "")).upper() for item in examples]
        valid_levels = [level for level in levels if level in ALLOWED_LEVELS]
        if valid_levels:
            level = Counter(valid_levels).most_common(1)[0][0]
            confidence = self._score_to_confidence(float(examples[0].get("score", 0.0)))
            fallback_reason = f"LLM fallback used nearest labeled resolution examples. {reason}"
        else:
            level = "L2"
            confidence = 0.35
            fallback_reason = f"Unable to retrieve examples; routed to assisted review. {reason}"

        return {
            "intent": intent,
            "sentiment": sentiment,
            "resolution_level": level,
            "confidence": confidence,
            "reason": fallback_reason.strip(),
        }

    @staticmethod
    def _extract_json_object(text: str) -> str:
        match = re.search(r"\{.*\}", text.strip(), flags=re.DOTALL)
        if not match:
            raise ValueError("No JSON object found.")
        return match.group(0)

    @staticmethod
    def _extract_text_field(text: str, label: str) -> str:
        match = re.search(rf"^{re.escape(label)}:\s*(.*)$", text, flags=re.MULTILINE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        return sum(a * b for a, b in zip(left, right))

    @staticmethod
    def _score_to_confidence(score: float) -> float:
        if score <= 0:
            return 0.45
        return max(0.45, min(0.82, score))


@lru_cache(maxsize=1)
def _default_engine() -> ResolutionDecisionEngine:
    return ResolutionDecisionEngine()


def resolve_query_level(query: str, intent: str, sentiment: str) -> dict[str, Any]:
    """Public orchestration entrypoint for L1/L2/L3 resolution routing."""
    return _default_engine().resolve_query_level(query, intent, sentiment)
