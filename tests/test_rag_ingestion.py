"""Unit tests for pharmasense.retrieval.ingestion.build_chunk_rows.

No database and no model download: exercises the chunk-building /
repeated-body redundancy logic directly against DeterministicFakeEmbedder.
"""
from datetime import date

from pharmasense.retrieval.embeddings import DeterministicFakeEmbedder
from pharmasense.retrieval.ingestion import SourceDocument, build_chunk_rows, content_hash


def _doc(doc_id, full_text, **overrides):
    defaults = dict(
        doc_id=doc_id,
        compound_id="CMP-0001",
        trial_id="TRL-0001",
        doc_type="Lab Notebook Entry",
        title=f"Title for {doc_id}",
        date=date(2024, 1, 1),
        tags="Safety,R&D",
        full_text=full_text,
    )
    defaults.update(overrides)
    return SourceDocument(**defaults)


def test_chunk_rows_preserve_document_metadata():
    embedder = DeterministicFakeEmbedder(dimension=16)
    doc = _doc("DOC-0001", "Some short body text.", trial_id=None)

    rows = build_chunk_rows(doc, embedder, seen_hashes={})

    assert len(rows) == 1
    row = rows[0]
    assert row.doc_id == "DOC-0001"
    assert row.compound_id == "CMP-0001"
    assert row.trial_id is None  # nullable trial_id preserved as None
    assert row.doc_type == "Lab Notebook Entry"
    assert row.title == "Title for DOC-0001"
    assert row.date == date(2024, 1, 1)
    assert row.tags == "Safety,R&D"


def test_chunk_rows_stamp_embedding_model_and_index_version():
    embedder = DeterministicFakeEmbedder(model_name="fake-v1", dimension=16)
    doc = _doc("DOC-0001", "Body text.")

    rows = build_chunk_rows(doc, embedder, seen_hashes={}, index_version="phase3-v1")

    assert rows[0].embedding_model == "fake-v1"
    assert rows[0].index_version == "phase3-v1"


def test_chunk_embedding_dimension_matches_embedder():
    embedder = DeterministicFakeEmbedder(dimension=24)
    doc = _doc("DOC-0001", "Body text.")

    rows = build_chunk_rows(doc, embedder, seen_hashes={})

    assert len(rows[0].embedding) == 24


def test_repeated_body_text_across_documents_is_flagged_as_duplicate():
    embedder = DeterministicFakeEmbedder(dimension=16)
    boilerplate = "SOP deviation report: temperature excursion noted during incubation."
    doc_a = _doc("DOC-0001", boilerplate)
    doc_b = _doc("DOC-0002", boilerplate)

    seen_hashes = {}
    rows_a = build_chunk_rows(doc_a, embedder, seen_hashes)
    rows_b = build_chunk_rows(doc_b, embedder, seen_hashes)

    assert rows_a[0].is_duplicate is False
    assert rows_a[0].duplicate_of_chunk_id is None

    assert rows_b[0].is_duplicate is True
    assert rows_b[0].duplicate_of_chunk_id == rows_a[0].chunk_id
    assert rows_b[0].content_hash == rows_a[0].content_hash == content_hash(boilerplate)

    # Both documents still get their own stored chunk row - neither is dropped.
    assert rows_a[0].doc_id == "DOC-0001"
    assert rows_b[0].doc_id == "DOC-0002"


def test_different_body_text_is_never_flagged_as_duplicate():
    embedder = DeterministicFakeEmbedder(dimension=16)
    doc_a = _doc("DOC-0001", "First unique body.")
    doc_b = _doc("DOC-0002", "Second, different body.")

    seen_hashes = {}
    rows_a = build_chunk_rows(doc_a, embedder, seen_hashes)
    rows_b = build_chunk_rows(doc_b, embedder, seen_hashes)

    assert rows_a[0].is_duplicate is False
    assert rows_b[0].is_duplicate is False
