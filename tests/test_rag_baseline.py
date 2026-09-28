"""Integration tests for phase3.baseline against real Postgres +
pgvector. Skipped automatically if no database is reachable (see
tests/conftest.py::pgvector_engine).

Uses synthetic fixtures and DeterministicFakeEmbedder to validate the
scoring/report-writing logic itself - independent of golden_set.json
and the real BGEEmbedder, which are only meant to be run together
(python -m phase3.baseline) for a production-meaningful number.
"""
import json
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from phase3.baseline import GoldenQuery, run_baseline, write_report
from phase3.db.models import DocumentChunk
from phase3.embeddings import DeterministicFakeEmbedder

from tests.rag_helpers import make_research_document

EMBEDDER = DeterministicFakeEmbedder(dimension=8)


def _add_chunk(session, chunk_id, doc_id, text):
    row = DocumentChunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        compound_id=None,
        trial_id=None,
        doc_type="Lab Notebook Entry",
        title="t",
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
    session.add(row)
    session.flush()
    return row


def test_run_baseline_scores_hits_and_misses(pgvector_engine):
    with Session(pgvector_engine) as session:
        make_research_document(session, "DOC-0001", "alpha passage")
        make_research_document(session, "DOC-0002", "beta passage")
        _add_chunk(session, "DOC-0001::chunk::0", "DOC-0001", "alpha passage")
        _add_chunk(session, "DOC-0002::chunk::0", "DOC-0002", "beta passage")
        session.commit()

        golden_set = [
            GoldenQuery(query="alpha passage", expected_doc_ids=["DOC-0001"], top_k=5),
            GoldenQuery(query="alpha passage", expected_doc_ids=["DOC-9999"], top_k=5),
        ]

        report = run_baseline(session, EMBEDDER, golden_set=golden_set)

        assert report["total_queries"] == 2
        assert report["hits"] == 1
        assert report["hit_rate_at_k"] == 0.5
        assert report["per_query"][0]["hit"] is True
        assert report["per_query"][1]["hit"] is False


def test_run_baseline_scores_expect_empty_queries(pgvector_engine):
    with Session(pgvector_engine) as session:
        make_research_document(session, "DOC-0001", "alpha passage")
        _add_chunk(session, "DOC-0001::chunk::0", "DOC-0001", "alpha passage")
        session.commit()

        golden_set = [
            GoldenQuery(
                query="alpha passage",
                expect_empty=True,
                filters={"compound_id": "CMP-9999"},
                top_k=5,
            ),
        ]

        report = run_baseline(session, EMBEDDER, golden_set=golden_set)

        assert report["hits"] == 1
        assert report["per_query"][0]["retrieved_doc_ids"] == []


def test_write_report_produces_valid_reloadable_json(pgvector_engine, tmp_path):
    with Session(pgvector_engine) as session:
        golden_set = [GoldenQuery(query="", expect_empty=True, top_k=5)]
        report = run_baseline(session, EMBEDDER, golden_set=golden_set)

    path = write_report(report, out_dir=tmp_path)

    assert path.exists()
    reloaded = json.loads(path.read_text())
    assert reloaded["total_queries"] == 1
    assert (tmp_path / "retrieval_baseline_latest.json").exists()
