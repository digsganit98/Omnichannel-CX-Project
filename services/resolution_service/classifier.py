import inspect
import json
import logging
import re
from collections import Counter
from functools import lru_cache
from typing import Any

from services.pii_service.masker import mask_text, unmask_text
from services.rag_service.groq_generator import GroqGenerator
from services.resolution_service.prompts import build_resolution_prompt
from services.resolution_service.resolution_loader import ResolutionExampleLoader

logger = logging.getLogger(__name__)

ALLOWED_LEVELS = {"L1", "L2", "L3"}
# L2's definition names two different things - "a backend/data lookup specific to this customer"
# and "operational approval" - and only the second needs a person. Both arrived as plain "L2", so
# a customer asking WHY a claim was rejected and one demanding it be HONOURED were indistinguishable
# to every rule downstream; the intent label is identical too (claim_status), so nothing could tell
# them apart. "lookup" is the default everywhere it is missing or unrecognised: unknown input must
# not manufacture tickets, and that keeps the old behaviour when the field is absent.
ALLOWED_L2_KINDS = {"lookup", "action"}
DEFAULT_L2_KIND = "lookup"
DEFAULT_TOP_K = 5

# ── Deterministic safety net ─────────────────────────────────────────────────
# A single LLM misjudgment (or a fallback default firing during an outage) must never
# silently under-classify a genuinely critical case. These patterns force L3 BEFORE the
# LLM is even called, independent of retrieval/LLM availability. Over-triggering here is
# the safe failure direction (assisted/critical review instead of auto-resolution), so the
# list is intentionally broad rather than narrow.
HIGH_RISK_PATTERNS = [
    r"\bfraud(ulent)?\b",
    r"\bhack(ed|ing)?\b",
    r"\bphishing\b",
    r"\bscam(med)?\b",
    r"\bstolen\b",
    r"\b(un)?authori[sz]ed\b",
    r"\bwithout my (permission|authori[sz]ation|consent|knowledge)\b",
    r"\bidentity theft\b",
    r"\bsim[\s-]?swap(ped)?\b",
    r"\bforg(ed|ery)\b",
    r"\baccount (has been |was )?(hacked|compromised|frozen)\b",
    r"\bshared (my )?otp\b",
    r"\botp\b.*\b(shared|gave|told)\b",
    r"\bdata (leak(ed)?|breach)\b",
    r"\blegal (complaint|action|notice)\b",
    r"\b(rbi )?ombudsman\b",
    r"\bconsumer court\b",
    r"\bblackmail(ed|ing)?\b",
    r"\bthreat(en(ed|ing)?)?\b",
    r"\bextortion\b",
    r"\bransom\b",
    r"\bmoney (is )?missing\b",
    r"\blost my phone\b.*\b(bank|app|logged in)\b",
]
_HIGH_RISK_REGEX = re.compile("|".join(HIGH_RISK_PATTERNS), flags=re.IGNORECASE)


def _high_risk_match(query: str) -> str | None:
    match = _HIGH_RISK_REGEX.search(query or "")
    return match.group(0) if match else None


class ResolutionDecisionEngine:
    """Classifies support queries into L1/L2/L3 using examples, vectors, and LLM reasoning."""

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
        self.fallback_generator = fallback_generator if fallback_generator is not None else self._try_ollama_generator()

    def resolve_query_level(self, query: str, intent: str, sentiment: str) -> dict[str, Any]:
        clean_query = (query or "").strip()
        clean_intent = str(intent or "unknown").strip()
        clean_sentiment = str(sentiment or "neutral").strip()

        if not clean_query:
            return self._fallback_decision(clean_intent, clean_sentiment, [], "Empty query received.")

        # ── Safety net FIRST, before retrieval or any LLM call ──────────────────────
        risk_term = _high_risk_match(clean_query)
        if risk_term:
            logger.warning(
                "resolution_high_risk_keyword_forced_l3",
                extra={"matched_term": risk_term, "intent": clean_intent},
            )
            return {
                "intent": clean_intent,
                "sentiment": clean_sentiment,
                "resolution_level": "L3",
                # L3 escalates unconditionally, so the kind is never consulted; carried only
                # so every decision dict has the same shape.
                "l2_kind": DEFAULT_L2_KIND,
                "confidence": 0.95,
                "reason": f"Deterministic safety net matched high-risk term '{risk_term}'.",
            }

        # Retrieval uses the raw query (embeddings stay within our own OpenSearch/local
        # infra, not a third party, and a masked placeholder would hurt similarity
        # matching against the plain-text labeled examples). Masking happens only right
        # before the query leaves the system to the LLM, below.
        examples = self.retrieve_similar_examples(clean_query, top_k=DEFAULT_TOP_K)
        masked_query, pii_mapping = mask_text(clean_query)
        prompt = build_resolution_prompt(masked_query, clean_intent, clean_sentiment, examples)
        llm_result = self._call_llm(prompt, clean_intent)

        if llm_result.get("llm_used") and llm_result.get("text"):
            unmasked_text = unmask_text(llm_result["text"], pii_mapping)
            parsed = self._parse_llm_json(unmasked_text, clean_intent, clean_sentiment)
            if parsed:
                return parsed
            logger.warning("resolution_llm_json_parse_failed", extra={"text": llm_result.get("text", "")[:500]})

        reason = llm_result.get("error") or "LLM did not return a usable decision."
        return self._fallback_decision(clean_intent, clean_sentiment, examples, reason)

    def retrieve_similar_examples(self, query: str, top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
        try:
            self._ensure_examples_indexed()
            hits = self.store.similarity_search(query, k=top_k, doc_type="resolution_example")
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
        count = self.store.count_documents(doc_type="resolution_example")
        if count >= len(documents):
            return
        self.store.index_documents(documents, recreate=False)

    def index_examples(self, recreate: bool = False) -> dict:
        """Explicitly (re)index the labeled resolution examples. Mirrors RAGPipeline.index()."""
        documents = self.loader.load_documents()
        result = self.store.index_documents(documents, recreate=recreate)
        return {"examples_loaded": len(documents), **result}

    @staticmethod
    def _hit_to_example(hit: dict[str, Any]) -> dict[str, Any]:
        metadata = hit.get("metadata", {})
        text = hit.get("text", "")
        return {
            "customer_query": ResolutionDecisionEngine._extract_text_field(text, "Customer Query"),
            "intent": metadata.get("intent", ""),
            "resolution_level": metadata.get("resolution_level", ""),
            "reason": metadata.get("reason", "") or ResolutionDecisionEngine._extract_text_field(text, "Reason"),
            "score": round(float(hit.get("score", 0.0)), 4),
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

    def _call_llm(self, prompt: str, intent: str = "unknown") -> dict[str, Any]:
        try:
            if isinstance(self.generator, GroqGenerator):
                result = self.generator._generate(
                    system_prompt="You are a BFSI resolution classifier. Return ONLY valid JSON.",
                    user_prompt=prompt,
                    operation="resolution_level_classification",
                    metadata={"intent": intent},
                )
            elif self.generator.__class__.__name__ == "OllamaGenerator":
                result = self.generator._generate(
                    prompt, operation="resolution_level_classification", metadata={"intent": intent}
                )
            elif hasattr(self.generator, "_generate"):
                # Unknown generator type. Label the call like the two branches above so
                # its usage is attributed to this operation rather than falling through
                # to the unlabelled 'llm_generation' default — but only when the callable
                # actually accepts the kwarg: signatures here vary (some take a single
                # positional prompt, some take system/user prompts and no operation), and
                # passing it blindly raises TypeError instead of classifying.
                try:
                    accepts_operation = "operation" in inspect.signature(
                        self.generator._generate).parameters
                except (TypeError, ValueError):
                    accepts_operation = False
                if accepts_operation:
                    result = self.generator._generate(
                        prompt, operation="resolution_level_classification",
                        metadata={"intent": intent},
                    )
                else:
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
            if self.fallback_generator.__class__.__name__ == "OllamaGenerator":
                return self.fallback_generator._generate(
                    prompt, operation="resolution_level_classification", metadata={"intent": intent, "fallback": True}
                )
            return self.fallback_generator._generate(
                system_prompt="You are a BFSI resolution classifier. Return ONLY valid JSON.",
                user_prompt=prompt,
                operation="resolution_level_classification",
                metadata={"intent": intent, "fallback": True},
            )
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
        # Same RAG_BACKEND switch the KB uses. The resolution examples are a
        # second doc_type in the SAME store, so they follow the KB backend
        # rather than needing a switch of their own.
        from services.rag_service.rag_pipeline import build_vector_store

        return build_vector_store()

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

        # Validated like the level above rather than trusted: an unrecognised value defaults
        # to lookup, so a malformed reply degrades to today's behaviour instead of escalating.
        l2_kind = str(payload.get("l2_kind") or "").strip().lower()
        if l2_kind not in ALLOWED_L2_KINDS:
            l2_kind = DEFAULT_L2_KIND

        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        return {
            "intent": str(payload.get("intent") or intent),
            "sentiment": str(payload.get("sentiment") or sentiment),
            "resolution_level": level,
            "l2_kind": l2_kind,
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
            logger.warning(
                "resolution_fallback_used",
                extra={"mode": "majority_vote_examples", "level": level, "reason": reason},
            )
        else:
            # No examples retrieved at all (e.g. OpenSearch/embedding infra outage). Default to
            # L2, NOT L1 — fail toward caution so an outage never silently under-prioritizes a
            # potentially risky case that the deterministic keyword net didn't catch.
            level = "L2"
            confidence = 0.35
            fallback_reason = f"Unable to retrieve examples; routed to assisted review. {reason}"
            logger.warning(
                "resolution_fallback_used",
                extra={"mode": "no_examples_default_l2", "reason": reason},
            )

        return {
            "intent": intent,
            "sentiment": sentiment,
            "resolution_level": level,
            # Both fallbacks land here: a majority vote over labelled examples, and the
            # no-examples default of L2 during an infra outage. Neither read the message, so
            # neither can claim the customer demanded an outcome - lookup, which does not
            # escalate on its own. An outage must not start manufacturing approval tickets.
            "l2_kind": DEFAULT_L2_KIND,
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
