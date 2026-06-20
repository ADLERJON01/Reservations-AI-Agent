"""One-time KB ingestion: FAQ jsonl → KnowledgeChunks → ChromaDB (cosine).

Idempotent: recreates the collection each run. Heavy deps imported lazily.
Run: python -m app.rag.ingest
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from app.config import get_settings
from app.models.retrieval import KnowledgeChunk
from app.rag.retriever import COLLECTION_NAME


def load_faq_chunks(path: Path) -> List[KnowledgeChunk]:
    """One Q+A per chunk (FAQs are short — no chunking)."""
    chunks: List[KnowledgeChunk] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        q, a = (r.get("question") or "").strip(), (r.get("answer") or "").strip()
        chunks.append(KnowledgeChunk(
            chunk_id=f"faq_{i:03d}",
            document_id="pestana_faq",
            source_type="faq",
            title=q,
            text=f"{q}\n\n{a}".strip(),
            source_url_or_path=r.get("source_url"),
            metadata={
                "question": q, "answer": a, "topic": r.get("topic"),
                "subtopic": r.get("subtopic"), "source_url": r.get("source_url"),
                "language": r.get("language"), "source_type": "faq",
            },
        ))
    return chunks


def build_index() -> int:
    from chromadb import PersistentClient                # lazy
    from sentence_transformers import SentenceTransformer  # lazy

    s = get_settings()
    chunks = load_faq_chunks(s.kb_path)
    model = SentenceTransformer(s.embedding_model)
    embeddings = model.encode([c.text for c in chunks], normalize_embeddings=True).tolist()

    client = PersistentClient(path=str(s.chroma_path))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    col = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    # Chroma rejects None metadata values — drop them.
    metadatas = [{k: v for k, v in c.metadata.items() if v is not None} for c in chunks]
    col.add(ids=[c.chunk_id for c in chunks], embeddings=embeddings,
            documents=[c.text for c in chunks], metadatas=metadatas)
    print(f"indexed {len(chunks)} chunks into '{COLLECTION_NAME}' at {s.chroma_path} "
          f"(model={s.embedding_model})")
    return len(chunks)


if __name__ == "__main__":
    build_index()
