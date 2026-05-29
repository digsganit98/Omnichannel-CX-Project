from services.rag_service.config import rag_top_k
from services.rag_service.documents import load_knowledge_documents
from services.rag_service.generator import OllamaGenerator
from services.rag_service.opensearch_store import OpenSearchVectorStore


class RAGPipeline:
    def __init__(self) -> None:
        self.store = OpenSearchVectorStore()
        self.generator = OllamaGenerator()

    def index(self, recreate: bool = False) -> dict:
        documents = load_knowledge_documents()
        result = self.store.index_documents(documents, recreate=recreate)
        return {"documents_loaded": len(documents), **result}

    def health(self) -> dict:
        return self.store.health()

    def answer(self, query: str, top_k: int | None = None) -> dict:
        contexts = self.store.similarity_search(query, k=top_k or rag_top_k())
        generation = self.generator.generate_answer(query, contexts)
        if generation["llm_used"] and generation["text"]:
            answer = generation["text"]
        elif contexts:
            answer = contexts[0]["text"]
        else:
            answer = "I could not find enough knowledge base context. A support ticket should be created."
        confidence = contexts[0]["score"] if contexts else 0.0
        return {
            "answer": answer,
            "confidence": confidence,
            "contexts": contexts,
            "llm": generation,
        }
