from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.rag_service.rag_pipeline import RAGPipeline

router = APIRouter(prefix="/rag", tags=["rag"])


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


@router.post("/query")
def query_rag(payload: RAGQuery) -> dict:
    try:
        return RAGPipeline().answer(payload.query, top_k=payload.top_k)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
