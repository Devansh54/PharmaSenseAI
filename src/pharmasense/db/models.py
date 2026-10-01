"""SQLAlchemy ORM model for the Phase 3 document_chunks table.

Reuses the same declarative Base as Phase 1 (pharmasense.db.source_schema.Base) so
both phases share one metadata object and one Alembic migration
history, rather than a second, disconnected schema.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text

from pgvector.sqlalchemy import Vector

from pharmasense.db.source_schema import Base
from pharmasense.config import EMBEDDING_DIM


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    chunk_id = Column(String(40), primary_key=True)
    doc_id = Column(String(20), ForeignKey("research_documents.doc_id"), nullable=False)

    # Denormalized from research_documents so retrieval can filter and
    # display citations without a join, and so a chunk still carries
    # this metadata even if the source row is later edited.
    compound_id = Column(String(20), ForeignKey("compounds.compound_id"), nullable=True)
    trial_id = Column(String(20), ForeignKey("clinical_trials.trial_id"), nullable=True)
    doc_type = Column(String(50))
    title = Column(String(300))
    date = Column(Date)
    tags = Column(String(300))

    chunk_index = Column(Integer, nullable=False)
    chunk_count = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=False)

    # Repeated-body redundancy handling: chunks with byte-identical
    # text (e.g. boilerplate reused verbatim across documents) share a
    # content_hash. Every occurrence after the first is flagged
    # is_duplicate and points at the canonical chunk via
    # duplicate_of_chunk_id, but the row - and its source document -
    # is never deleted.
    content_hash = Column(String(64), nullable=False)
    is_duplicate = Column(Boolean, nullable=False, default=False)
    duplicate_of_chunk_id = Column(String(40), ForeignKey("document_chunks.chunk_id"), nullable=True)

    embedding = Column(Vector(EMBEDDING_DIM), nullable=False)
    embedding_model = Column(String(100), nullable=False)
    index_version = Column(String(20), nullable=False)

    created_at = Column(DateTime, nullable=False)
