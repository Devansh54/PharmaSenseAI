"""PharmaSense Phase 3: RAG foundation over research_documents.full_text.

Provides document-preserving chunking, embeddings (BAAI/bge-small-en-v1.5),
pgvector storage with exact cosine search, metadata/entity filtered top-k
retrieval, resolvable evidence references, and an initial labeled
retrieval baseline. See phase3.retrieval.search for the main entry point
later phases should call.
"""
