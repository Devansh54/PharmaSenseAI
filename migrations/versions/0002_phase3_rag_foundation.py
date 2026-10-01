"""Phase 3 RAG foundation: pgvector extension + document_chunks table

Revision ID: 0002_phase3_rag_foundation
Revises: 0001_initial_schema
Create Date: 2026-09-28

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0002_phase3_rag_foundation"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("chunk_id", sa.String(40), primary_key=True),
        sa.Column("doc_id", sa.String(20), sa.ForeignKey("research_documents.doc_id"), nullable=False),
        sa.Column("compound_id", sa.String(20), sa.ForeignKey("compounds.compound_id"), nullable=True),
        sa.Column("trial_id", sa.String(20), sa.ForeignKey("clinical_trials.trial_id"), nullable=True),
        sa.Column("doc_type", sa.String(50)),
        sa.Column("title", sa.String(300)),
        sa.Column("date", sa.Date()),
        sa.Column("tags", sa.String(300)),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "duplicate_of_chunk_id", sa.String(40), sa.ForeignKey("document_chunks.chunk_id"), nullable=True
        ),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column("index_version", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_index("ix_document_chunks_doc_id", "document_chunks", ["doc_id"])
    op.create_index("ix_document_chunks_compound_id", "document_chunks", ["compound_id"])
    op.create_index("ix_document_chunks_trial_id", "document_chunks", ["trial_id"])
    op.create_index("ix_document_chunks_doc_type", "document_chunks", ["doc_type"])
    op.create_index("ix_document_chunks_content_hash", "document_chunks", ["content_hash"])
    op.create_index("ix_document_chunks_index_version", "document_chunks", ["index_version"])

    # Deliberately no ivfflat/hnsw ANN index: retrieval uses pgvector's
    # `<=>` cosine-distance operator with a plain sequential scan,
    # which is exact (not approximate) similarity search.


def downgrade() -> None:
    op.drop_index("ix_document_chunks_index_version", table_name="document_chunks")
    op.drop_index("ix_document_chunks_content_hash", table_name="document_chunks")
    op.drop_index("ix_document_chunks_doc_type", table_name="document_chunks")
    op.drop_index("ix_document_chunks_trial_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_compound_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_doc_id", table_name="document_chunks")
    op.drop_table("document_chunks")
