"""Retriever interface + the concrete ChromaDB retriever.

The Retriever protocol is what the RAG agent depends on (inject a fake in tests).
ChromaRetriever imports chromadb / sentence-transformers LAZILY so this module
imports fine without the [rag] extra installed.

Score semantics: the collection is built with cosine space and NORMALIZED
embeddings, so ChromaDB returns cosine distance in [0, 2]; we report
score = 1 - distance (higher = more similar) and also keep raw_distance.
"""
from __future__ import annotations

from typing import List, Optional, Protocol

from app.config import get_settings
from app.models.retrieval import RetrievalSource

COLLECTION_NAME = "pestana_kb"


class Retriever(Protocol):
    def retrieve(self, query: str, *, top_k: int = 3) -> List[RetrievalSource]:
        ...


class ChromaRetriever:
    """Cosine retrieval over the FAQ index. Heavy deps imported lazily."""

    def __init__(self, collection_name: str = COLLECTION_NAME) -> None:
        from chromadb import PersistentClient            # lazy
        from sentence_transformers import SentenceTransformer  # lazy

        s = get_settings()
        self._model = SentenceTransformer(s.embedding_model)
        client = PersistentClient(path=str(s.chroma_path))
        self._col = client.get_collection(collection_name)

    def retrieve(self, query: str, *, top_k: int = 3) -> List[RetrievalSource]:
        emb = self._model.encode([query], normalize_embeddings=True).tolist()
        res = self._col.query(query_embeddings=emb, n_results=top_k,
                              include=["documents", "metadatas", "distances"])
        sources: List[RetrievalSource] = []
        ids = res["ids"][0]
        for i in range(len(ids)):
            dist = float(res["distances"][0][i])
            meta = res["metadatas"][0][i] or {}
            sources.append(RetrievalSource(
                source_id=ids[i],
                source_title=meta.get("question") or meta.get("title"),
                source_url_or_path=meta.get("source_url"),
                chunk_text=res["documents"][0][i],
                score=1.0 - dist,
                raw_distance=dist,
                source_type=meta.get("source_type", "faq"),
                metadata=meta,
            ))
        return sources


_DEFAULT: Optional[ChromaRetriever] = None


def get_default_retriever() -> ChromaRetriever:
    """Lazily build the default ChromaRetriever (loads the model + index once)."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = ChromaRetriever()
    return _DEFAULT
