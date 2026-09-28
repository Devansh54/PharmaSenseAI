"""Integration tests for phase3.references.resolve_reference against
real Postgres + pgvector. Skipped automatically if no database is
reachable (see tests/conftest.py::pgvector_engine).
"""
import pytest
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from phase3.config import EMBEDDING_DIM
from phase3.db.models import DocumentChunk
from phase3.embeddings import DeterministicFakeEmbedder
from phase3.references import ReferenceNotFoundError, resolve_reference

from tests.rag_helpers import make_research_document

EMBEDDER = DeterministicFakeEmbedder(dimension=EMBEDDING_DIM)


def _add_chunk(session, chunk_id, doc_id, text, **overrides):
    defaults = dict(
        chunk_id=chunk_id,
        doc_id=doc_id,
        compound_id="CMP-0001",
        trial_id=None,
        doc_type="Regulatory Briefing",
        title="A resolvable title",
        date=date(2024, 3, 1),
        tags="Safety",
        chunk_index=0,
        chunk_count=1,
        chunk_text=text,
        token_count=len(text.split()),
        content_hash="hash-" + chunk_id,
        is_duplicate=False,
        duplicate_of_chunk_id=None,
        embedding=EMBEDDER.embed([text])[0],
        embedding_model=EMBEDDER.model_name,
        index_version="phase3-v1",
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    row = DocumentChunk(**defaults)
    session.add(row)
    session.flush()
    return row


def test_resolve_reference_returns_full_citation(pgvector_engine):
    with Session(pgvector_engine) as session:
        make_research_document(session, "DOC-0001", "full body text", author="Jane Reviewer")
        _add_chunk(session, "DOC-0001::chunk::0", "DOC-0001", "full body text")
        session.commit()

        ref = resolve_reference(session, "DOC-0001::chunk::0")

        assert ref.chunk_id == "DOC-0001::chunk::0"
        assert ref.doc_id == "DOC-0001"
        assert ref.title == "A resolvable title"
        assert ref.author == "Jane Reviewer"
        assert ref.doc_type == "Regulatory Briefing"
        assert ref.chunk_text == "full body text"
        assert ref.source_document_exists is True


def test_resolve_reference_flags_missing_source_document(pgvector_engine):
    with Session(pgvector_engine) as session:
        make_research_document(session, "DOC-0001", "full body text")
        _add_chunk(session, "DOC-0001::chunk::0", "DOC-0001", "full body text")
        session.commit()

        # Simulate the parent document row being gone while the chunk
        # citation (deliberately) survives.
        from phase1.db.models import ResearchDocument

        session.query(ResearchDocument).filter(ResearchDocument.doc_id == "DOC-0001").delete()
        session.commit()

        ref = resolve_reference(session, "DOC-0001::chunk::0")
        assert ref.source_document_exists is False
        assert ref.chunk_text == "full body text"


def test_resolve_reference_raises_for_unknown_chunk_id(pgvector_engine):
    with Session(pgvector_engine) as session:
        with pytest.raises(ReferenceNotFoundError):
            resolve_reference(session, "NOPE::chunk::0")
