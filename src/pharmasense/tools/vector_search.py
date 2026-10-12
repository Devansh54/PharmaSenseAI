"""Vector Search Tool for retrieving evidence from the research documents corpus."""
from typing import Dict, List, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pharmasense.retrieval.retrieval import (
    search,
    lexical_search,
    extract_compound_identifier,
    RetrievalFilters,
)
from pharmasense.retrieval.embeddings import BGEEmbedder, EmbeddingProvider

class VectorSearchInput(BaseModel):
    query: str
    top_k: int = 5
    metadata_filters: Dict[str, Any] | None = None

class VectorSearchOutput(BaseModel):
    chunks: List[dict]
    index_version: str

_GLOBAL_EMBEDDER = None

def get_embedder() -> EmbeddingProvider:
    global _GLOBAL_EMBEDDER
    if _GLOBAL_EMBEDDER is None:
        try:
            _GLOBAL_EMBEDDER = BGEEmbedder()
        except Exception as e:
            import logging
            from pharmasense.retrieval.embeddings import DeterministicFakeEmbedder
            logging.getLogger(__name__).warning(
                "Failed to initialize BGEEmbedder (%s); falling back to DeterministicFakeEmbedder", e
            )
            _GLOBAL_EMBEDDER = DeterministicFakeEmbedder()
    return _GLOBAL_EMBEDDER

def vector_search_tool(
    session: Session,
    input_data: VectorSearchInput,
    embedder: EmbeddingProvider | None = None
) -> VectorSearchOutput:
    """Search the document chunks using local embeddings or lexical compound lookup."""
    filters_dict = input_data.metadata_filters or {}
    compound_id = filters_dict.get("compound_id") or extract_compound_identifier(input_data.query)

    filters = RetrievalFilters(
        doc_type=filters_dict.get("doc_type"),
        compound_id=compound_id,
        trial_id=filters_dict.get("trial_id")
    )

    if compound_id:
        results = lexical_search(
            session=session,
            compound_id=compound_id,
            top_k=input_data.top_k,
            filters=filters
        )
    else:
        active_embedder = embedder or get_embedder()
        results = search(
            session=session,
            query=input_data.query,
            embedder=active_embedder,
            top_k=input_data.top_k,
            filters=filters
        )

    from pharmasense.validation.security import detect_injection

    chunks = []
    for r in results:
        if detect_injection(r.chunk_text):
            safe_text = "[CONTENT BLOCKED DUE TO PROMPT INJECTION SCREENING]"
        else:
            safe_text = r.chunk_text

        chunks.append({
            "chunk_id": r.reference.chunk_id,
            "doc_id": r.reference.doc_id,
            "title": r.reference.title,
            "chunk_text": safe_text,
            "similarity_score": r.score
        })

    return VectorSearchOutput(chunks=chunks, index_version="phase3-v1")
