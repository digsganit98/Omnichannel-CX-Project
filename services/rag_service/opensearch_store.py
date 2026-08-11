from opensearchpy import OpenSearch, helpers

from langchain_core.documents import Document

from services.rag_service.config import embedding_dimension, opensearch_index, opensearch_url
from services.rag_service.embeddings import SemanticEmbeddings


class OpenSearchVectorStore:
    def __init__(self) -> None:
        self.client = OpenSearch(
            hosts=[opensearch_url()],
            timeout=30,
            max_retries=3,
            retry_on_timeout=True,
        )
        self.index_name = opensearch_index()
        self.dimension = embedding_dimension()
        self.embeddings = SemanticEmbeddings(self.dimension)

    def health(self) -> dict:
        return {
            "opensearch_url": opensearch_url(),
            "index": self.index_name,
            "cluster": self.client.cluster.health(),
            "index_exists": self.client.indices.exists(index=self.index_name),
            "embeddings": self.embeddings.status(),
        }

    def create_index(self, recreate: bool = False) -> None:
        if recreate and self.client.indices.exists(index=self.index_name):
            self.client.indices.delete(index=self.index_name)
        if self.client.indices.exists(index=self.index_name):
            return
        self.client.indices.create(
            index=self.index_name,
            body={
                "settings": {
                    "index": {
                        "knn": True,
                        "knn.algo_param.ef_search": 100,
                    }
                },
                "mappings": {
                    "properties": {
                        "text": {"type": "text"},
                        "metadata": {"type": "object", "enabled": True},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": self.dimension,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "lucene",
                            },
                        },
                    }
                },
            },
        )

    def index_documents(self, documents: list[Document], recreate: bool = False) -> dict:
        self.create_index(recreate=recreate)
        texts = [document.page_content for document in documents]
        vectors = self.embeddings.embed_documents(texts)
        actions = []
        for index, (document, vector) in enumerate(zip(documents, vectors)):
            actions.append(
                {
                    "_index": self.index_name,
                    "_id": f"{document.metadata.get('source', 'doc')}::{index}",
                    "_source": {
                        "text": document.page_content,
                        "metadata": document.metadata,
                        "embedding": vector,
                    },
                }
            )
        success, errors = helpers.bulk(self.client, actions, stats_only=False, raise_on_error=False)
        self.client.indices.refresh(index=self.index_name)
        return {"indexed": success, "errors": len(errors)}

    def count_documents(self, doc_type: str = "knowledge_base") -> int:
        """Return total number of documents indexed under the given doc_type."""
        if not self.client.indices.exists(index=self.index_name):
            return 0
        response = self.client.count(
            index=self.index_name,
            body={"query": {"term": {"metadata.doc_type.keyword": doc_type}}},
        )
        return response.get("count", 0)

    def list_documents(self, limit: int = 20) -> list[dict]:
        """Return a sample of indexed document chunks with metadata."""
        if not self.client.indices.exists(index=self.index_name):
            return []
        response = self.client.search(
            index=self.index_name,
            body={
                "size": limit,
                "query": {"term": {"metadata.doc_type.keyword": "knowledge_base"}},
                "_source": ["text", "metadata"],
            },
        )
        hits = response.get("hits", {}).get("hits", [])
        return [
            {
                "id": hit["_id"],
                "text_preview": hit["_source"]["text"][:200],
                "source": hit["_source"].get("metadata", {}).get("source", "unknown"),
                "doc_type": hit["_source"].get("metadata", {}).get("doc_type", ""),
            }
            for hit in hits
        ]

    def similarity_search(self, query: str, k: int = 4, doc_type: str = "knowledge_base") -> list[dict]:
        vector = self.embeddings.embed_query(query)
        response = self.client.search(
            index=self.index_name,
            body={
                "size": k,
                "query": {
                    "bool": {
                        "must": [{
                            "knn": {
                                "embedding": {
                                    "vector": vector,
                                    "k": k,
                                }
                            }
                        }],
                        "filter": [{"term": {"metadata.doc_type.keyword": doc_type}}],
                    }
                },
            },
        )
        hits = response.get("hits", {}).get("hits", [])
        return [
            {
                "text": hit["_source"]["text"],
                "metadata": {**hit["_source"].get("metadata", {}), "retrieval": "opensearch_vector"},
                "score": round(float(hit.get("_score", 0.0)), 4),
            }
            for hit in hits
        ]
