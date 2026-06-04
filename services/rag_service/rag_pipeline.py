import logging

from services.rag_service.config import rag_top_k
from services.rag_service.documents import load_knowledge_documents
from services.rag_service.groq_generator import GroqGenerator
from services.rag_service.opensearch_store import OpenSearchVectorStore
from services.retrieval_service.hybrid_search import HybridSearch

logger = logging.getLogger(__name__)


class RAGPipeline:
    def __init__(self, store=None, generator=None) -> None:
        self.store = store or OpenSearchVectorStore()
        self.generator = generator or GroqGenerator()

    def index(self, recreate: bool = False) -> dict:
        documents = load_knowledge_documents()
        result = self.store.index_documents(documents, recreate=recreate)
        return {"documents_loaded": len(documents), **result}

    def health(self) -> dict:
        return self.store.health()

    def answer(self, query: str, conversation_context: dict | None = None, top_k: int | None = None) -> dict:
        retrieval_backend = "opensearch_vector"
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
                retrieval_error = retrieval_error or "opensearch returned no knowledge_base contexts"
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
        elif contexts:
            answer = f"{contexts[0]['text']}\n\nSource: [1] {citations[0]['source']}"
        else:
            answer = "I could not find enough verified knowledge to answer this request. A support ticket has been created."
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
