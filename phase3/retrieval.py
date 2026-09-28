"""Retrieval over document_chunks using pgvector exact cosine search.

The single entry point (search()) other code should call, kept
provider-independent from the embedding backend via EmbeddingProvider -
matching the LLMGateway/LLMProvider pattern from Phase 2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from phase3.config import DEFAULT_TOP_K
from phase3.db.models import DocumentChunk
from phase3.embeddings import EmbeddingProvider


@dataclass(frozen=True)
class RetrievalFilters:
    """Metadata/entity filters applied before ranking by similarity."""

    compound_id: Optional[str] = None
    trial_id: Optional[str] = None
    doc_type: Optional[str] = None
    tag: Optional[str] = None
    date_from: Optional[date_type] = None
    date_to: Optional[date_type] = None
    index_version: Optional[str] = None
    include_duplicates: bool = False


@dataclass(frozen=True)
class EvidenceReference:
    """A resolvable pointer back to the exact source passage."""

    chunk_id: str
    doc_id: str
    title: Optional[str]
    doc_type: Optional[str]
    date: Optional[date_type]
    compound_id: Optional[str]
    trial_id: Optional[str]
    tags: Optional[str]


@dataclass(frozen=True)
class RetrievalResult:
    reference: EvidenceReference
    chunk_text: str
    score: float  # cosine similarity in [-1, 1]; higher is more similar
    is_duplicate: bool
    duplicate_of_chunk_id: Optional[str]


def _to_result(row: DocumentChunk, distance: float) -> RetrievalResult:
    # pgvector's cosine_distance() is 1 - cosine_similarity; convert
    # back to a similarity score so higher always means "more similar".
    similarity = 1.0 - distance
    return RetrievalResult(
        reference=EvidenceReference(
            chunk_id=row.chunk_id,
            doc_id=row.doc_id,
            title=row.title,
            doc_type=row.doc_type,
            date=row.date,
            compound_id=row.compound_id,
            trial_id=row.trial_id,
            tags=row.tags,
        ),
        chunk_text=row.chunk_text,
        score=similarity,
        is_duplicate=row.is_duplicate,
        duplicate_of_chunk_id=row.duplicate_of_chunk_id,
    )


def search(
    session: Session,
    query: str,
    embedder: EmbeddingProvider,
    top_k: int = DEFAULT_TOP_K,
    filters: Optional[RetrievalFilters] = None,
    min_score: Optional[float] = None,
) -> List[RetrievalResult]:
    """Return up to top_k chunks most similar to query.

    Uses pgvector's `<=>` cosine-distance operator directly (an exact,
    sequential-scan comparison against every matching row - no
    approximate/ANN index is involved). Returns an empty list, never
    an error, when nothing matches: an empty/blank query, an index
    with no matching rows, filters that exclude everything, or (when
    min_score is set) no result meeting the relevance threshold.
    Callers should treat an empty list as "no evidence" and answer
    accordingly rather than guessing.

    Calibrating a good min_score threshold for a given embedding model
    is evaluation-tuning work left to a later phase; Phase 3 only
    provides the mechanism.
    """
    if not query or not query.strip():
        return []

    filters = filters or RetrievalFilters()
    [query_vector] = embedder.embed([query])
    distance_expr = DocumentChunk.embedding.cosine_distance(query_vector)

    stmt = select(DocumentChunk, distance_expr.label("distance"))

    if not filters.include_duplicates:
        stmt = stmt.where(DocumentChunk.is_duplicate.is_(False))
    if filters.compound_id is not None:
        stmt = stmt.where(DocumentChunk.compound_id == filters.compound_id)
    if filters.trial_id is not None:
        stmt = stmt.where(DocumentChunk.trial_id == filters.trial_id)
    if filters.doc_type is not None:
        stmt = stmt.where(DocumentChunk.doc_type == filters.doc_type)
    if filters.tag is not None:
        stmt = stmt.where(DocumentChunk.tags.ilike(f"%{filters.tag}%"))
    if filters.date_from is not None:
        stmt = stmt.where(DocumentChunk.date >= filters.date_from)
    if filters.date_to is not None:
        stmt = stmt.where(DocumentChunk.date <= filters.date_to)
    if filters.index_version is not None:
        stmt = stmt.where(DocumentChunk.index_version == filters.index_version)
    if min_score is not None:
        stmt = stmt.where(distance_expr <= (1.0 - min_score))

    stmt = stmt.order_by(distance_expr).limit(top_k)

    rows = session.execute(stmt).all()
    return [_to_result(row, distance) for row, distance in rows]
