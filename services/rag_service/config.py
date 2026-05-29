import os


def opensearch_url() -> str:
    return os.getenv("OPENSEARCH_URL", "http://localhost:9200")


def opensearch_index() -> str:
    return os.getenv("OPENSEARCH_INDEX", "cx_knowledge_base")


def embedding_dimension() -> int:
    return int(os.getenv("RAG_EMBEDDING_DIM", "384"))


def ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")


def rag_top_k() -> int:
    return int(os.getenv("RAG_TOP_K", "4"))
