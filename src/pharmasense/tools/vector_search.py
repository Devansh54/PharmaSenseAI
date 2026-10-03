"""Vector Search Tool for retrieving evidence from the research documents corpus."""
from typing import Dict, List, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pharmasense.retrieval.retrieval import search, RetrievalFilters
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
        _GLOBAL_EMBEDDER = BGEEmbedder()
    return _GLOBAL_EMBEDDER

def vector_search_tool(
    session: Session, 
    input_data: VectorSearchInput,
    embedder: EmbeddingProvider | None = None
) -> VectorSearchOutput:
    """Search the document chunks using local embeddings."""
    active_embedder = embedder or get_embedder()
    
    filters_dict = input_data.metadata_filters or {}
    filters = RetrievalFilters(
        doc_type=filters_dict.get("doc_type"),
        compound_id=filters_dict.get("compound_id"),
        trial_id=filters_dict.get("trial_id")
    )
    
    results = search(
        session=session,
        query=input_data.query,
        embedder=active_embedder,
        top_k=input_data.top_k,
        filters=filters
    )
    
    chunks = [
        {
            "chunk_id": r.reference.chunk_id,
            "doc_id": r.reference.doc_id,
            "title": r.reference.title,
            "chunk_text": r.chunk_text,
            "similarity_score": r.score
        }
        for r in results
    ]
    
    return VectorSearchOutput(chunks=chunks, index_version="phase3-v1")
