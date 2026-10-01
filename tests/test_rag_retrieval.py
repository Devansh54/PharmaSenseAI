"""Integration tests for pharmasense.retrieval.retrieval.search against real
Postgres + pgvector. Skipped automatically if no database is reachable
(see tests/conftest.py::pgvector_engine).
"""
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from pharmasense.config import EMBEDDING_DIM
from pharmasense.db.models import DocumentChunk
from pharmasense.retrieval.embeddings import DeterministicFakeEmbedder
from pharmasense.retrieval.retrieval import RetrievalFilters, search

from tests.rag_helpers import make_compound, make_research_document

EMBEDDER = DeterministicFakeEmbedder(dimension=EMBEDDING_DIM)


def _add_chunk(session, chunk_id, doc_id, text, **overrides):
    defaults = dict(
        chunk_id=chunk_id,
        doc_id=doc_id,
        compound_id=None,
        trial_id=None,
        doc_type="Lab Notebook Entry",
        title=f"Title {chunk_id}",
        date=date(2024, 1, 1),
        tags="",
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


def test_search_returns_exact_text_match_as_top_result(pgvector_engine):
    with Session(pgvector_engine) as session:
        make_research_document(session, "DOC-0001", "target passage")
        make_research_document(session, "DOC-0002", "unrelated passage")
        _add_chunk(session, "DOC-0001::chunk::0", "DOC-0001", "target passage")
        _add_chunk(session, "DOC-0002::chunk::0", "DOC-0002", "unrelated passage")
        session.commit()

        results = search(session, "target passage", EMBEDDER, top_k=1)

        assert len(results) == 1
        assert results[0].reference.doc_id == "DOC-0001"
        assert results[0].score > 0.99


def test_search_respects_top_k(pgvector_engine):
    with Session(pgvector_engine) as session:
        for i in range(5):
            doc_id = f"DOC-000{i}"
            make_research_document(session, doc_id, f"passage number {i}")
            _add_chunk(session, f"{doc_id}::chunk::0", doc_id, f"passage number {i}")
        session.commit()

        results = search(session, "passage number 0", EMBEDDER, top_k=2)

        assert len(results) == 2


def test_metadata_filters_restrict_results(pgvector_engine):
    with Session(pgvector_engine) as session:
        make_compound(session, "CMP-0001")
        make_compound(session, "CMP-0002")
        make_research_document(session, "DOC-0001", "passage one", compound_id="CMP-0001")
        make_research_document(session, "DOC-0002", "passage two", compound_id="CMP-0002")
        _add_chunk(session, "DOC-0001::chunk::0", "DOC-0001", "passage one", compound_id="CMP-0001")
        _add_chunk(session, "DOC-0002::chunk::0", "DOC-0002", "passage two", compound_id="CMP-0002")
        session.commit()

        results = search(
            session, "passage", EMBEDDER, top_k=5, filters=RetrievalFilters(compound_id="CMP-0001")
        )

        assert [r.reference.doc_id for r in results] == ["DOC-0001"]


def test_doc_type_and_tag_filters(pgvector_engine):
    with Session(pgvector_engine) as session:
        make_research_document(session, "DOC-0001", "passage one")
        make_research_document(session, "DOC-0002", "passage two")
        _add_chunk(
            session, "DOC-0001::chunk::0", "DOC-0001", "passage one",
            doc_type="Regulatory Briefing", tags="Safety,Cardiology",
        )
        _add_chunk(
            session, "DOC-0002::chunk::0", "DOC-0002", "passage two",
            doc_type="Internal Memo", tags="R&D",
        )
        session.commit()

        by_doc_type = search(session, "passage", EMBEDDER, top_k=5, filters=RetrievalFilters(doc_type="Regulatory Briefing"))
        assert [r.reference.doc_id for r in by_doc_type] == ["DOC-0001"]

        by_tag = search(session, "passage", EMBEDDER, top_k=5, filters=RetrievalFilters(tag="Cardiology"))
        assert [r.reference.doc_id for r in by_tag] == ["DOC-0001"]


def test_duplicates_excluded_by_default_and_included_on_request(pgvector_engine):
    with Session(pgvector_engine) as session:
        make_research_document(session, "DOC-0001", "canonical passage")
        make_research_document(session, "DOC-0002", "canonical passage")
        _add_chunk(session, "DOC-0001::chunk::0", "DOC-0001", "canonical passage", is_duplicate=False)
        _add_chunk(
            session, "DOC-0002::chunk::0", "DOC-0002", "canonical passage",
            is_duplicate=True, duplicate_of_chunk_id="DOC-0001::chunk::0",
        )
        session.commit()

        default_results = search(session, "canonical passage", EMBEDDER, top_k=5)
        assert [r.reference.doc_id for r in default_results] == ["DOC-0001"]

        with_dupes = search(
            session, "canonical passage", EMBEDDER, top_k=5, filters=RetrievalFilters(include_duplicates=True)
        )
        assert {r.reference.doc_id for r in with_dupes} == {"DOC-0001", "DOC-0002"}


def test_empty_index_returns_empty_list(pgvector_engine):
    with Session(pgvector_engine) as session:
        results = search(session, "anything at all", EMBEDDER, top_k=5)
    assert results == []


def test_impossible_filter_returns_empty_list(pgvector_engine):
    with Session(pgvector_engine) as session:
        make_research_document(session, "DOC-0001", "passage one")
        _add_chunk(session, "DOC-0001::chunk::0", "DOC-0001", "passage one")
        session.commit()

        results = search(
            session, "passage", EMBEDDER, top_k=5, filters=RetrievalFilters(compound_id="CMP-9999")
        )
    assert results == []


def test_blank_query_returns_empty_list_without_querying_db(pgvector_engine):
    with Session(pgvector_engine) as session:
        results = search(session, "   ", EMBEDDER, top_k=5)
    assert results == []


def test_min_score_threshold_filters_out_low_relevance_matches(pgvector_engine):
    with Session(pgvector_engine) as session:
        make_research_document(session, "DOC-0001", "target passage")
        make_research_document(session, "DOC-0002", "completely unrelated other text")
        _add_chunk(session, "DOC-0001::chunk::0", "DOC-0001", "target passage")
        _add_chunk(session, "DOC-0002::chunk::0", "DOC-0002", "completely unrelated other text")
        session.commit()

        results = search(session, "target passage", EMBEDDER, top_k=5, min_score=0.99)

        # Only the exact-text match clears a 0.99 similarity threshold.
        assert [r.reference.doc_id for r in results] == ["DOC-0001"]
