import os


def opensearch_url() -> str:
    return os.getenv("OPENSEARCH_URL", "http://localhost:9200")


def opensearch_index() -> str:
    return os.getenv("OPENSEARCH_INDEX", "cx_knowledge_base")


def embedding_dimension() -> int:
    return int(os.getenv("RAG_EMBEDDING_DIM", "384"))


def embedding_backend() -> str:
    return os.getenv("EMBEDDING_BACKEND", "sentence_transformers")


def embedding_model() -> str:
    return os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


def rag_top_k() -> int:
    return int(os.getenv("RAG_TOP_K", "4"))
