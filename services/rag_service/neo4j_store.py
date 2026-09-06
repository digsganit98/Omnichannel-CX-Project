"""KB vector store backed by Neo4j instead of OpenSearch.

Same six-method interface as OpenSearchVectorStore, so RAGPipeline and the
resolution classifier take either one without knowing which. Selected by
RAG_BACKEND=neo4j.

Why this exists: the KB is 14 chunks over one PDF, and OpenSearch is a whole
second datastore (1.34 GB image) carried for it. Neo4j already holds every
customer record, and vector indexes have been GA there since 5.15 - the
deployed image is 5.26.26. Putting KB chunks in the same database removes a
container AND makes Phase 2 possible: a (:KBChunk) can be linked to the
(:Product) it describes, so retrieval can follow the customer's own holdings
instead of matching text in isolation. That link is what a separate search
engine structurally cannot do.

Chunks are (:KBChunk) nodes; nothing here touches the seeded BFSI graph.
"""

import logging

from langchain_core.documents import Document

from services.neo4j_service.client import Neo4jClient
from services.rag_service.config import (
    embedding_dimension,
    kb_graph_filter_enabled,
    kb_vector_index,
)
from services.rag_service.embeddings import SemanticEmbeddings

logger = logging.getLogger(__name__)


class Neo4jVectorStore:
    def __init__(self, client: Neo4jClient | None = None) -> None:
        self.client = client or Neo4jClient()
        self.dimension = embedding_dimension()
        self.index_name = kb_vector_index()
        self.embeddings = SemanticEmbeddings(self.dimension)

    # ── lifecycle ────────────────────────────────────────────────────────────

    def health(self) -> dict:
        try:
            counts = self.client.query(
                "MATCH (k:KBChunk) RETURN count(k) AS chunks"
            )
            chunk_count = counts[0]["chunks"] if counts else 0
            indexes = self.client.query(
                "SHOW VECTOR INDEXES YIELD name, state WHERE name = $name "
                "RETURN name, state",
                {"name": self.index_name},
            )
            index_state = indexes[0]["state"] if indexes else None
        except Exception as exc:  # surfaced, not swallowed - see create_index
            return {
                "backend": "neo4j_vector",
                "index": self.index_name,
                "error": str(exc),
                "embeddings": self.embeddings.status(),
            }
        return {
            "backend": "neo4j_vector",
            "index": self.index_name,
            "index_state": index_state,
            "index_exists": index_state is not None,
            "chunks": chunk_count,
            "embeddings": self.embeddings.status(),
        }

    def create_index(self, recreate: bool = False) -> None:
        """Create the vector index, and drop the chunks first when recreating.

        `recreate` drops (:KBChunk) nodes, not just the index - re-indexing
        without that leaves chunks from a previous run behind, because the
        MERGE key below is the chunk id, and a changed chunking produces
        different ids rather than overwriting the old ones.
        """
        if recreate:
            self.client.write("MATCH (k:KBChunk) DETACH DELETE k")
            self.client.write(f"DROP INDEX {self.index_name} IF EXISTS")
        self.client.write(
            f"""
            CREATE VECTOR INDEX {self.index_name} IF NOT EXISTS
            FOR (k:KBChunk) ON (k.embedding)
            OPTIONS {{indexConfig: {{
                `vector.dimensions`: {self.dimension},
                `vector.similarity_function`: 'cosine'
            }}}}
            """
        )

    # ── writing ──────────────────────────────────────────────────────────────

    def index_documents(self, documents: list[Document], recreate: bool = False) -> dict:
        self.create_index(recreate=recreate)
        texts = [document.page_content for document in documents]
        vectors = self.embeddings.embed_documents(texts)
        indexed = 0
        errors = 0
        for position, (document, vector) in enumerate(zip(documents, vectors)):
            metadata = document.metadata or {}
            chunk_id = f"{metadata.get('source', 'doc')}::{position}"
            try:
                self.client.write(
                    """
                    MERGE (k:KBChunk {chunk_id: $chunk_id})
                    SET k.text = $text,
                        k.source = $source,
                        k.doc_type = $doc_type,
                        k.document_version = $document_version,
                        k.embedding = $embedding
                    """,
                    {
                        "chunk_id": chunk_id,
                        "text": document.page_content,
                        "source": str(metadata.get("source", "")),
                        "doc_type": str(metadata.get("doc_type", "knowledge_base")),
                        "document_version": str(metadata.get("document_version", "")),
                        "embedding": vector,
                    },
                )
                indexed += 1
            except Exception as exc:
                errors += 1
                logger.warning(
                    "kb_chunk_write_failed",
                    extra={"chunk_id": chunk_id, "error": str(exc)},
                )
        return {"indexed": indexed, "errors": errors}

    # ── reading ──────────────────────────────────────────────────────────────

    def count_documents(self, doc_type: str = "knowledge_base") -> int:
        rows = self.client.query(
            "MATCH (k:KBChunk {doc_type: $doc_type}) RETURN count(k) AS total",
            {"doc_type": doc_type},
        )
        return rows[0]["total"] if rows else 0

    def list_documents(self, limit: int = 20) -> list[dict]:
        rows = self.client.query(
            """
            MATCH (k:KBChunk {doc_type: 'knowledge_base'})
            RETURN k.chunk_id AS id, k.text AS text, k.source AS source,
                   k.doc_type AS doc_type
            LIMIT $limit
            """,
            {"limit": limit},
        )
        return [
            {
                "id": row["id"],
                "text_preview": (row["text"] or "")[:200],
                "source": row["source"] or "unknown",
                "doc_type": row["doc_type"] or "",
            }
            for row in rows
        ]

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        doc_type: str = "knowledge_base",
        customer_id: str | None = None,
    ) -> list[dict]:
        """Vector search over (:KBChunk).

        `customer_id` is Phase 2 and optional: when supplied AND KB_GRAPH_FILTER
        is on, chunks linked to a product the customer actually holds are
        preferred. Callers that pass nothing get plain vector search - byte for
        byte the behaviour of the OpenSearch path.
        """
        vector = self.embeddings.embed_query(query)
        # Over-fetch, then filter by doc_type in Cypher: the vector index has no
        # pre-filter, so asking for exactly k and discarding some leaves fewer
        # than k results.
        candidates = max(k * 5, 20)
        rows = self.client.query(
            f"""
            CALL db.index.vector.queryNodes($index, $candidates, $vector)
            YIELD node, score
            WHERE node.doc_type = $doc_type
            RETURN node.text AS text, node.source AS source,
                   node.doc_type AS doc_type, node.chunk_id AS chunk_id,
                   score
            ORDER BY score DESC
            LIMIT $k
            """,
            {
                "index": self.index_name,
                "candidates": candidates,
                "vector": vector,
                "doc_type": doc_type,
                "k": k,
            },
        )
        results = [
            {
                "text": row["text"],
                "metadata": {
                    "source": row["source"],
                    "doc_type": row["doc_type"],
                    "chunk_id": row["chunk_id"],
                    "retrieval": "neo4j_vector",
                },
                "score": round(float(row["score"] or 0.0), 4),
            }
            for row in rows
        ]
        if customer_id and kb_graph_filter_enabled():
            results = self._prefer_customer_products(results, customer_id, k)
        return results

    # ── Phase 2: graph-aware retrieval ───────────────────────────────────────

    def _prefer_customer_products(
        self, results: list[dict], customer_id: str, k: int
    ) -> list[dict]:
        """Re-rank so chunks about products this customer holds come first.

        Re-ranks rather than filters. A hard filter would answer "how do I
        report a lost card?" with nothing for a customer who holds no card,
        when the honest answer is the general procedure.
        """
        try:
            rows = self.client.query(
                """
                MATCH (c:Customer {customer_id: $customer_id})-[]->(holding)
                MATCH (holding)-[:PRODUCT_IS]->(p:Product)<-[:ABOUT]-(k:KBChunk)
                RETURN DISTINCT k.chunk_id AS chunk_id
                """,
                {"customer_id": customer_id},
            )
        except Exception as exc:
            logger.warning("kb_graph_filter_failed", extra={"error": str(exc)})
            return results
        owned = {row["chunk_id"] for row in rows}
        if not owned:
            return results
        for result in results:
            if result["metadata"].get("chunk_id") in owned:
                result["metadata"]["customer_product_match"] = True
        results.sort(
            key=lambda r: (
                not r["metadata"].get("customer_product_match", False),
                -r["score"],
            )
        )
        return results[:k]
