"""SQLAlchemy ORM model for the Phase 3 document_chunks table.

Reuses the same declarative Base as Phase 1 (pharmasense.db.source_schema.Base) so
both phases share one metadata object and one Alembic migration
history, rather than a second, disconnected schema.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, Float

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


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    task_id = Column(String(40), primary_key=True)
    event_id = Column(String(20), ForeignKey("adverse_events.event_id"), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")  # PENDING, REVIEWED
    reason = Column(String(500), nullable=False)
    created_at = Column(DateTime, nullable=False)


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    decision_id = Column(String(40), primary_key=True)
    task_id = Column(String(40), ForeignKey("review_tasks.task_id"), nullable=False)
    reviewer_id = Column(String(50), nullable=False)
    decision = Column(String(50), nullable=False)
    comments = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)


class RuntimeTrace(Base):
    """Parent trace for a single complete orchestration request."""
    __tablename__ = "runtime_traces"

    trace_id = Column(String(50), primary_key=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    latency_sec = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)
    total_tokens = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False) # SUCCESS, ERROR, BLOCKED
    error_code = Column(String(100), nullable=True)

    # Versioning
    app_version = Column(String(20), nullable=False)
    workflow_version = Column(String(20), nullable=False)
    dataset_version = Column(String(20), nullable=False)

    escalated = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False)


class RuntimeEvent(Base):
    """Child event representing a single node execution, LLM call, or tool invocation within a trace."""
    __tablename__ = "runtime_events"

    event_id = Column(String(50), primary_key=True)
    trace_id = Column(String(50), ForeignKey("runtime_traces.trace_id"), nullable=False)
    event_type = Column(String(50), nullable=False) # PLANNER, SPECIALIST, TOOL, LLM, GUARDRAIL, FINALIZER
    node_name = Column(String(100), nullable=False)

    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    latency_sec = Column(Float, nullable=True)

    prompt_version = Column(String(20), nullable=True)
    tool_version = Column(String(20), nullable=True)
    model_name = Column(String(50), nullable=True)
    model_version = Column(String(50), nullable=True)
    index_version = Column(String(20), nullable=True) # RAG

    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_cost = Column(Float, nullable=True)

    status = Column(String(20), nullable=False) # SUCCESS, ERROR

    # Use Text for serialized JSON metadata.
    # NEVER store raw user_prompt or raw report_content here.
    event_metadata = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False)
