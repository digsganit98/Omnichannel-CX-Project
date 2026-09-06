import logging

from services.rag_service.config import rag_backend, rag_top_k
from services.rag_service.documents import load_knowledge_documents
from services.rag_service.groq_generator import GroqGenerator
from services.rag_service.opensearch_store import OpenSearchVectorStore
from services.retrieval_service.hybrid_search import HybridSearch

logger = logging.getLogger(__name__)


def build_vector_store():
    """Return the KB vector store named by RAG_BACKEND.

    Imported lazily so a deployment running one backend never imports the
    other's driver - opensearchpy is not installed everywhere Neo4j is.
    """
    if rag_backend() == "neo4j":
        from services.rag_service.neo4j_store import Neo4jVectorStore

        return Neo4jVectorStore()
    return OpenSearchVectorStore()


class RAGPipeline:
    def __init__(self, store=None, generator=None) -> None:
        self.store = store or build_vector_store()
        self.generator = generator or GroqGenerator()

    def index(self, recreate: bool = False) -> dict:
        documents = load_knowledge_documents()
        result = self.store.index_documents(documents, recreate=recreate)
        return {"documents_loaded": len(documents), **result}

    def health(self) -> dict:
        return self.store.health()

    def answer(self, query: str, conversation_context: dict | None = None, top_k: int | None = None) -> dict:
        # Names the store that actually answered, so a trace shows which backend
        # ran. "neo4j_vector" is deliberately NOT "neo4j_graph": the latter is in
        # CUSTOMER_RECORD_BACKENDS (orchestration_agents.py:856), which gates two
        # escalation rules. A KB answer is not a customer-record answer, and a
        # substring match on "neo4j" here would silently change when replies are
        # held for a human.
        vector_backend = (
            "neo4j_vector" if rag_backend() == "neo4j" else "opensearch_vector"
        )
        retrieval_backend = vector_backend
        retrieval_error = None
        try:
            contexts = self.store.similarity_search(query, k=top_k or rag_top_k())
        except Exception as exc:
            retrieval_backend = "keyword_fallback"
            retrieval_error = str(exc)
            logger.warning("rag_vector_retrieval_failed", extra={"error": retrieval_error})
            contexts = self._local_contexts(query)
        contexts = self._customer_safe_contexts(contexts)
        local_contexts = self._local_contexts(query)
        if local_contexts:
            if not contexts:
                retrieval_backend = "keyword_fallback"
                retrieval_error = retrieval_error or f"{vector_backend} returned no knowledge_base contexts"
                contexts = local_contexts
            elif self._should_prefer_local_context(query, contexts[0], local_contexts[0]):
                retrieval_backend = "hybrid_keyword_rerank"
                retrieval_error = retrieval_error or "keyword rerank selected a stronger KB FAQ match"
                contexts = local_contexts + [
                    context
                    for context in contexts
                    if context.get("metadata", {}).get("source") != local_contexts[0]["metadata"]["source"]
                ]
        generation = self.generator.generate_answer(query, contexts, conversation_context)
        citations = [
            {"index": index, "source": item["metadata"].get("source", "unknown"), "score": item["score"]}
            for index, item in enumerate(contexts, start=1)
        ]
        if generation["llm_used"] and generation["text"]:
            answer = generation["text"]
        else:
            # LLM unavailable (e.g. provider rate-limit/error) or produced no text.
            # Never surface a raw KB passage + internal "Source: [1] ..." citation to the
            # customer — that leaks internals and often doesn't match the question. Degrade
            # to a clean holding message; the system decides separately whether to ticket,
            # so we do not promise one here.
            answer = (
                "I'm having trouble accessing that information right now. "
                "Let me connect you with a support specialist who can help you further."
            )
        return {
            "answer": answer,
            "confidence": contexts[0]["score"] if contexts else 0.0,
            "contexts": contexts,
            "citations": citations,
            "llm": generation,
            "retrieval_backend": retrieval_backend,
            "retrieval_error": retrieval_error,
        }

    @staticmethod
    def _local_contexts(query: str) -> list[dict]:
        result = HybridSearch().search(query)
        if not result:
            return []
        return [{
            "text": result.answer,
            "score": result.score,
            "metadata": {
                "source": result.source,
                "doc_type": "knowledge_base",
                "document_version": "local-v1",
                "retrieval": "keyword_fallback",
            },
        }]

    @staticmethod
    def _customer_safe_contexts(contexts: list[dict]) -> list[dict]:
        return [
            context
            for context in contexts
            if context.get("metadata", {}).get("doc_type") == "knowledge_base"
        ]

    @staticmethod
    def _should_prefer_local_context(query: str, vector_context: dict, local_context: dict) -> bool:
        vector_lexical_score = HybridSearch.score_text(query, vector_context.get("text", ""))
        local_score = float(local_context.get("score", 0.0))
        return local_score >= 0.35 and local_score >= vector_lexical_score
