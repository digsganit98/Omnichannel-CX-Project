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


def rag_backend() -> str:
    """Which vector store backs KB retrieval: "opensearch" (default) or "neo4j".

    Both implement the same six-method interface, so this switches the whole
    retrieval path. Defaults to opensearch so an unset env var keeps the
    behaviour every existing deployment already has.
    """
    return os.getenv("RAG_BACKEND", "opensearch").strip().lower()


def kb_vector_index() -> str:
    """Name of the Neo4j vector index over (:KBChunk).embedding."""
    return os.getenv("KB_VECTOR_INDEX", "kb_chunk_embedding")


def kb_graph_filter_enabled() -> bool:
    """Phase 2: restrict KB retrieval to chunks linked to the customer's own products.

    Off by default - a customer whose holdings have no linked chunks would
    otherwise retrieve nothing at all, which is worse than an unfiltered answer.
    """
    return os.getenv("KB_GRAPH_FILTER", "false").strip().lower() == "true"
