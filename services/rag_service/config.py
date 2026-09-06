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
    """Which vector store backs KB retrieval: "neo4j" (default) or "opensearch".

    Both implement the same six-method interface, so this switches the whole
    retrieval path.

    Neo4j is the default because it measured identical - 18/18 same rank on the
    probe set with real embeddings - while removing a second datastore, and
    because it is the only one of the two that can hold the
    (:KBChunk)-[:ABOUT]->(:Product) edges that scope retrieval to what a
    customer actually holds.

    It also sidesteps a failure mode OpenSearch cannot avoid on a shared host:
    OpenSearch blocks ALL index creation above a 90% disk watermark and
    re-applies that block every ~90s, so the KB simply cannot be indexed on a
    full box no matter how small the index is. Neo4j has no such gate.

    Set RAG_BACKEND=opensearch to go back; nothing about that path changed.
    """
    return os.getenv("RAG_BACKEND", "neo4j").strip().lower()


def kb_vector_index() -> str:
    """Name of the Neo4j vector index over (:KBChunk).embedding."""
    return os.getenv("KB_VECTOR_INDEX", "kb_chunk_embedding")


def kb_graph_filter_enabled() -> bool:
    """Phase 2: restrict KB retrieval to chunks linked to the customer's own products.

    Off by default - a customer whose holdings have no linked chunks would
    otherwise retrieve nothing at all, which is worse than an unfiltered answer.
    """
    return os.getenv("KB_GRAPH_FILTER", "false").strip().lower() == "true"
