"""RAG (#6): conditional retrieval over the FAQ knowledge base.

Heavy deps (chromadb, sentence-transformers) are imported lazily inside the
concrete retriever / ingestion, so importing this package needs neither.
"""
