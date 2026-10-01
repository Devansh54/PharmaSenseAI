"""Resolve a chunk_id back to full, citable source detail.

So an answer can cite something a reviewer can actually open and
verify, rather than a bare similarity score.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from typing import Optional

from sqlalchemy.orm import Session

from pharmasense.db.source_schema import ResearchDocument
from pharmasense.db.models import DocumentChunk


@dataclass(frozen=True)
class ResolvedReference:
    chunk_id: str
    doc_id: str
    title: Optional[str]
    author: Optional[str]
    doc_type: Optional[str]
    date: Optional[date_type]
    compound_id: Optional[str]
    trial_id: Optional[str]
    tags: Optional[str]
    chunk_text: str
    chunk_index: int
    chunk_count: int
    source_document_exists: bool


class ReferenceNotFoundError(Exception):
    """Raised when chunk_id does not exist in document_chunks."""


def resolve_reference(session: Session, chunk_id: str) -> ResolvedReference:
    """Look up chunk_id and return its full, citable source detail.

    Raises ReferenceNotFoundError if the chunk itself is missing (e.g.
    a stale citation from a prior index version). Never mutates or
    deletes anything. source_document_exists is False if the parent
    research_documents row is gone even though the chunk citation
    (correctly) still resolves, so callers can flag a stale citation
    instead of presenting it as current.
    """
    chunk = session.get(DocumentChunk, chunk_id)
    if chunk is None:
        raise ReferenceNotFoundError(f"No document_chunks row for chunk_id={chunk_id!r}")

    doc = session.get(ResearchDocument, chunk.doc_id)
    return ResolvedReference(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        title=chunk.title,
        author=doc.author if doc else None,
        doc_type=chunk.doc_type,
        date=chunk.date,
        compound_id=chunk.compound_id,
        trial_id=chunk.trial_id,
        tags=chunk.tags,
        chunk_text=chunk.chunk_text,
        chunk_index=chunk.chunk_index,
        chunk_count=chunk.chunk_count,
        source_document_exists=doc is not None,
    )
