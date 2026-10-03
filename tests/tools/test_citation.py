"""Tests for Citation Formatter tool."""
from sqlalchemy.orm import Session
from pharmasense.tools.citation import citation_formatter_tool, CitationInput
from tests.rag_helpers import make_research_document
from pharmasense.db.models import DocumentChunk
from datetime import datetime, timezone, date

def test_citation_formatter(pgvector_engine):
    with Session(pgvector_engine) as session:
        make_research_document(session, "DOC-1", "Full text", author="Test Author", title="Doc Title")
        chunk = DocumentChunk(
            chunk_id="CHK-1", doc_id="DOC-1", chunk_index=0, chunk_count=1,
            chunk_text="text", token_count=1, content_hash="hash",
            embedding=[0.1]*384, embedding_model="bge", index_version="v1",
            title="Doc Title",
            created_at=datetime.now(timezone.utc)
        )
        session.add(chunk)
        session.commit()
        
        result = citation_formatter_tool(session, CitationInput(
            claim="Claim text",
            evidence_chunk_ids=["CHK-1", "NOPE-1"]
        ))
        
        assert result.claim == "Claim text"
        assert len(result.citations) == 1
        assert result.citations[0]["doc_id"] == "DOC-1"
        assert result.citations[0]["title"] == "Doc Title"
        assert result.invalid_chunk_ids == ["NOPE-1"]
