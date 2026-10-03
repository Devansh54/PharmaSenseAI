"""Tests for Vector Search tool."""
from sqlalchemy.orm import Session
from pharmasense.tools.vector_search import vector_search_tool, VectorSearchInput
from pharmasense.db.models import DocumentChunk
from tests.rag_helpers import make_research_document
from pharmasense.retrieval.embeddings import DeterministicFakeEmbedder
from pharmasense.config import EMBEDDING_DIM
from datetime import datetime, timezone, date

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
