from services.rag_service.config import rag_top_k
from services.rag_service.documents import load_knowledge_documents
from services.rag_service.generator import OllamaGenerator
from services.rag_service.opensearch_store import OpenSearchVectorStore
from services.retrieval_service.hybrid_search import HybridSearch


class RAGPipeline:
    def __init__(self, store=None, generator=None) -> None:
        self.store = store or OpenSearchVectorStore()
        self.generator = generator or OllamaGenerator()

    def index(self, recreate: bool = False) -> dict:
        documents = load_knowledge_documents()
        result = self.store.index_documents(documents, recreate=recreate)
        return {"documents_loaded": len(documents), **result}

    def health(self) -> dict:
        return self.store.health()

    def answer(self, query: str, conversation_context: dict | None = None, top_k: int | None = None) -> dict:
        try:
            contexts = self.store.similarity_search(query, k=top_k or rag_top_k())
        except Exception:
            contexts = self._local_contexts(query)
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
        }

    @staticmethod
    def _local_contexts(query: str) -> list[dict]:
        result = HybridSearch().search(query)
        if not result:
            return []
        return [{
            "text": result.answer,
            "score": result.score,
            "metadata": {"source": result.source, "document_version": "local-v1", "retrieval": "keyword_fallback"},
        }]
