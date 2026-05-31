import hashlib
import math
import os
import re

from langchain_core.embeddings import Embeddings


class HashingEmbeddings(Embeddings):
    """Small local embedding model for cost-free demos.

    This keeps the stack fully open-source and avoids paid APIs. It is deterministic,
    fast, and works with OpenSearch k-NN. For stronger semantic quality, replace this
    class with a sentence-transformers embedding implementation.
    """

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [round(value / norm, 6) for value in vector]


class SemanticEmbeddings(Embeddings):
    """Use sentence-transformers in deployed environments and hash vectors in lightweight tests."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension
        self.fallback = HashingEmbeddings(dimension)
        self.model = None
        if os.getenv("EMBEDDING_BACKEND", "hashing") == "sentence_transformers":
            try:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer(os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"))
            except ImportError:
                self.model = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.model:
            return self.model.encode(texts, normalize_embeddings=True).tolist()
        return self.fallback.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if self.model:
            return self.model.encode([text], normalize_embeddings=True)[0].tolist()
        return self.fallback.embed_query(text)
