from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api.dependencies.security import require_admin_auth
from services.rag_service.config import embedding_backend, embedding_model
from services.rag_service.config import rag_backend
from services.rag_service.rag_pipeline import RAGPipeline, build_vector_store

router = APIRouter(prefix="/admin/rag", tags=["admin"], dependencies=[Depends(require_admin_auth)])

_DIAGNOSTIC_QUERY = "What is the loan application process?"


class RAGQuery(BaseModel):
    query: str
    top_k: int | None = None


@router.get("/health")
def rag_health() -> dict:
    try:
        return RAGPipeline().health()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/index")
def build_rag_index(recreate: bool = False) -> dict:
    try:
        return RAGPipeline().index(recreate=recreate)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/index-resolution-examples")
def build_resolution_examples_index(recreate: bool = False) -> dict:
    """(Re)index the labeled L1/L2/L3 examples used by services.resolution_service."""
    try:
        from services.resolution_service import ResolutionDecisionEngine
        return ResolutionDecisionEngine().index_examples(recreate=recreate)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/link-kb-graph")
def link_kb_graph() -> dict:
    """Phase 2: link (:KBChunk) nodes to the (:Product) nodes they describe.

    Run AFTER /admin/rag/index with RAG_BACKEND=neo4j - it needs the chunks to
    exist. Idempotent, so re-running after a re-index is safe. Returns how many
    chunks were linked and how many were not; three are expected to stay
    unlinked (Demat, SIP, ELSS have no product in the catalogue).
    """
    if rag_backend() != "neo4j":
        raise HTTPException(
            status_code=400,
            detail=f"KB graph links require RAG_BACKEND=neo4j (currently '{rag_backend()}')",
        )
    try:
        from services.neo4j_service.client import Neo4jClient
        from services.rag_service.kb_graph_links import link_kb_chunks_to_graph

        client = Neo4jClient()
        try:
            return link_kb_chunks_to_graph(client)
        finally:
            client.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/query")
def query_rag(payload: RAGQuery) -> dict:
    return RAGPipeline().answer(payload.query, top_k=payload.top_k)


@router.get("/diagnostics")
def rag_diagnostics() -> dict:
    """Verify that the PDF is properly embedded and the knowledge base is retrievable.

    Returns chunk count, sample chunks, and the result of a test query so you can
    confirm at a glance whether the RAG pipeline is working end-to-end.
    """
    try:
        store = build_vector_store()
    except Exception as exc:
        return {"status": "vector_store_unreachable", "backend": rag_backend(), "error": str(exc)}

    try:
        total = store.count_documents()
    except Exception as exc:
        return {"status": "vector_store_unreachable", "backend": rag_backend(), "error": str(exc)}

    if total == 0:
        return {
            "status": "empty",
            "total_chunks_indexed": 0,
            "embedding_backend": embedding_backend(),
            "embedding_model": embedding_model(),
            "hint": "Run POST /admin/rag/index?recreate=true to index the knowledge base.",
        }

    sample_chunks = []
    try:
        sample_chunks = store.list_documents(limit=5)
    except Exception:
        pass

    test_result: dict = {}
    try:
        pipeline = RAGPipeline(store=store)
        result = pipeline.answer(_DIAGNOSTIC_QUERY, top_k=3)
        test_result = {
            "query": _DIAGNOSTIC_QUERY,
            "top_results": [
                {
                    "source": ctx.get("metadata", {}).get("source", "unknown"),
                    "score": ctx.get("score", 0.0),
                    "text_preview": ctx.get("text", "")[:200],
                }
                for ctx in result.get("contexts", [])
            ],
            "retrieval_backend": result.get("retrieval_backend"),
            "top_score": result["contexts"][0]["score"] if result.get("contexts") else 0.0,
        }
    except Exception as exc:
        test_result = {"error": str(exc)}

    top_score = test_result.get("top_score", 0.0)
    status = "ok" if total > 0 and top_score >= 0.3 else "low_confidence"

    return {
        "status": status,
        "total_chunks_indexed": total,
        "embedding_backend": embedding_backend(),
        "embedding_model": embedding_model(),
        "sample_chunks": sample_chunks,
        "test_query": test_result,
    }
