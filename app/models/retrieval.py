"""RAG (#6) contracts.

Thin & generic by intent: a FAQ is one KnowledgeChunk source_type; the retriever
deals in chunks/sources, not FAQ-specific shapes (so a future source type needs
no rewrite). NOT a loader/ingestion platform — that's deferred until a 2nd source
type actually exists.

RetrievalOutput carries debug/traceability fields beyond the locked
agent_output_schema.retrieval block (used + sources); those extras live in
runtime state only, not the persisted spec.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class KnowledgeChunk(BaseModel):
    """One indexed unit. For FAQs: one Q+A per chunk (no chunking)."""
    chunk_id: str
    document_id: str
    source_type: str = "faq"
    title: str                       # FAQ question (or doc/section title)
    text: str                        # the embedded text (question + answer)
    source_url_or_path: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class RetrievalSource(BaseModel):
    """One retrieved hit. The first 5 fields mirror the locked retrieval block."""
    source_id: str
    source_title: Optional[str] = None
    source_url_or_path: Optional[str] = None
    chunk_text: Optional[str] = None
    score: float                     # normalized cosine similarity = 1 - raw_distance
    raw_distance: Optional[float] = None
    source_type: str = "faq"
    metadata: dict = Field(default_factory=dict)


class RetrievalOutput(BaseModel):
    """Produced by the RAG agent. used=false when RAG didn't run."""
    used: bool = False
    sources: List[RetrievalSource] = Field(default_factory=list)
    # --- debug / traceability (runtime only; not in the locked schema) ---
    query_text: Optional[str] = None
    query_source: Optional[str] = None     # subject_plus_evidence | subject_plus_body_excerpt | body_clean_fallback
    embedding_model: Optional[str] = None
    top_k: Optional[int] = None
    threshold: Optional[float] = None
    kb_answerable: Optional[bool] = None
