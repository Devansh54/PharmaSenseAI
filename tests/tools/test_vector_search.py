"""Tests for Vector Search tool."""
import pytest
from datetime import datetime, timezone, date
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pharmasense.tools.vector_search import vector_search_tool, VectorSearchInput, VectorSearchOutput
from pharmasense.db.source_schema import Base
from pharmasense.db.models import DocumentChunk
from pharmasense.retrieval.retrieval import RetrievalResult, EvidenceReference
from tests.rag_helpers import make_research_document
from pharmasense.retrieval.embeddings import DeterministicFakeEmbedder
from pharmasense.config import EMBEDDING_DIM

def test_vector_search_tool(pgvector_engine):
    fake_embedder = DeterministicFakeEmbedder(dimension=EMBEDDING_DIM)
    
    with Session(pgvector_engine) as session:
        make_research_document(session, "DOC-VS1", "Test content")
        chunk = DocumentChunk(
            chunk_id="CHK-VS1", doc_id="DOC-VS1", chunk_index=0, chunk_count=1,
            chunk_text="Test content", token_count=2, content_hash="hash_vs",
            embedding=fake_embedder.embed(["Test content"])[0], 
            embedding_model="fake", index_version="v1",
            created_at=datetime.now(timezone.utc)
        )
        session.add(chunk)
        session.commit()
        
        result = vector_search_tool(
            session, 
            VectorSearchInput(query="Test", top_k=1),
            embedder=fake_embedder
        )
        
        assert len(result.chunks) == 1
        assert result.chunks[0]["chunk_id"] == "CHK-VS1"
        assert result.chunks[0]["similarity_score"] > 0


def test_matching_document_identifiers_preserves_citations():
    """Matches compound identifier in corpus and preserves source content and citation metadata."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        make_research_document(
            session,
            "DOC-001",
            "CMP-0001 showed good tolerance.",
            compound_id="CMP-0001",
            title="Study CMP-0001"
        )
        chunk = DocumentChunk(
            chunk_id="CHK-001",
            doc_id="DOC-001",
            compound_id="CMP-0001",
            title="Study CMP-0001",
            chunk_text="CMP-0001 showed good tolerance.",
            chunk_index=0,
            chunk_count=1,
            token_count=5,
            content_hash="hash1",
            embedding=[0.1] * EMBEDDING_DIM,
            embedding_model="fake",
            index_version="v1",
            created_at=datetime.now(timezone.utc),
        )
        session.add(chunk)
        session.commit()

        res = vector_search_tool(session, VectorSearchInput(query="CMP-0001", top_k=5))
        assert len(res.chunks) == 1
        assert res.chunks[0]["chunk_id"] == "CHK-001"
        assert res.chunks[0]["doc_id"] == "DOC-001"
        assert res.chunks[0]["title"] == "Study CMP-0001"
        assert res.chunks[0]["chunk_text"] == "CMP-0001 showed good tolerance."
        assert res.chunks[0]["similarity_score"] == 1.0


def test_excluding_irrelevant_vector_neighbours_for_explicit_identifier():
    """Arbitrary vector neighbours are not treated as evidence for an explicit identifier query."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        # Insert chunk for an unrelated compound
        make_research_document(
            session,
            "DOC-002",
            "Unrelated study on CMP-0002",
            compound_id="CMP-0002",
            title="Study CMP-0002"
        )
        chunk = DocumentChunk(
            chunk_id="CHK-002",
            doc_id="DOC-002",
            compound_id="CMP-0002",
            title="Study CMP-0002",
            chunk_text="Unrelated study on CMP-0002",
            chunk_index=0,
            chunk_count=1,
            token_count=5,
            content_hash="hash2",
            embedding=[0.2] * EMBEDDING_DIM,
            embedding_model="fake",
            index_version="v1",
            created_at=datetime.now(timezone.utc),
        )
        session.add(chunk)
        session.commit()

        # Query for unknown compound ZXQ-9999
        res = vector_search_tool(session, VectorSearchInput(query="ZXQ-9999", top_k=5))
        assert len(res.chunks) == 0


def test_completed_lookup_with_no_matches():
    """A completed corpus lookup with no matches returns a clean empty result."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        res = vector_search_tool(session, VectorSearchInput(query="ZXQ-9999", top_k=5))
        assert isinstance(res, VectorSearchOutput)
        assert res.chunks == []
        assert res.index_version == "phase3-v1"


def test_retrieval_errors_remain_distinct_from_empty():
    """Database execution errors are preserved and never converted into empty results."""
    mock_session = MagicMock()
    mock_session.execute.side_effect = RuntimeError("Database connection lost.")
    with pytest.raises(RuntimeError, match="Database connection lost."):
        vector_search_tool(mock_session, VectorSearchInput(query="ZXQ-9999"))


def test_existing_semantic_retrieval_unchanged_for_general_questions():
    """Ordinary semantic vector retrieval remains unchanged for general topic questions."""
    fake_embedder = DeterministicFakeEmbedder(dimension=EMBEDDING_DIM)
    with patch("pharmasense.tools.vector_search.search") as mock_search:
        mock_search.return_value = [
            RetrievalResult(
                reference=EvidenceReference(
                    chunk_id="CHK-GEN",
                    doc_id="DOC-GEN",
                    title="General Title",
                    doc_type="Review",
                    date=None,
                    compound_id=None,
                    trial_id=None,
                    tags=None,
                ),
                chunk_text="General safety passage",
                score=0.85,
                is_duplicate=False,
                duplicate_of_chunk_id=None,
            )
        ]
        mock_session = MagicMock()
        res = vector_search_tool(
            mock_session,
            VectorSearchInput(query="general oncology safety findings", top_k=3),
            embedder=fake_embedder,
        )
        mock_search.assert_called_once()
        assert len(res.chunks) == 1
        assert res.chunks[0]["chunk_id"] == "CHK-GEN"
        assert res.chunks[0]["similarity_score"] == 0.85

