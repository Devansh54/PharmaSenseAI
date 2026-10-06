"""
Eval database readiness guard tests.

These tests ensure that the persistent evaluation database (EVAL_DATABASE_URL
or the pharmasense_test fallback) has been properly bootstrapped before a live
S2 acceptance run can proceed. They are offline in the sense that they make no
LLM/API calls, but they DO require the database to be available.

Run the bootstrap script if these tests fail:
    $env:PYTHONPATH="src"
    .venv\\Scripts\\python.exe scratch/bootstrap_eval_db.py

These tests cover the EXACT failure mode that caused the live S2 run to return
0 chunks: the pharmasense_test database was empty because the pgvector_engine
pytest fixture creates+drops schema per-test-session, so the live harness
found an empty DB.
"""
import os
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

# Same resolution logic as conftest.py and the live harness
_DB_URL = os.environ.get(
    "EVAL_DATABASE_URL",
    os.environ.get(
        "PHARMASENSE_TEST_DATABASE_URL",
        "postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense_test",
    ),
)

# ── shared fixture ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def persistent_eval_engine():
    """Connect to the persistent eval DB (NOT the per-test fixture DB).

    Skips all tests in this module if the DB is unreachable — the live tests
    themselves will be skipped too in that case.
    """
    from sqlalchemy.exc import OperationalError
    engine = create_engine(_DB_URL)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip(f"Persistent eval DB unreachable at {_DB_URL}")
    yield engine


# ── guard tests ───────────────────────────────────────────────────────────────

def test_eval_db_has_document_chunks_table(persistent_eval_engine):
    """Fail fast if document_chunks table does not exist in the eval DB.

    This is the exact failure mode that caused the live S2 run to return
    0 chunks, because the harness connected to a bare empty database.
    """
    tables = inspect(persistent_eval_engine).get_table_names()
    assert "document_chunks" in tables, (
        "document_chunks table is missing from the eval DB. "
        "Run: python scratch/bootstrap_eval_db.py"
    )


def test_eval_db_has_research_documents(persistent_eval_engine):
    """Fail fast if research_documents is empty."""
    with persistent_eval_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM research_documents")).scalar()
    assert count > 0, (
        f"research_documents is empty ({count} rows). "
        "Run: python scratch/bootstrap_eval_db.py"
    )


def test_eval_db_document_chunks_populated(persistent_eval_engine):
    """Fail fast if document_chunks is empty (schema present but no ingestion ran)."""
    with persistent_eval_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM document_chunks")).scalar()
    assert count > 0, (
        f"document_chunks has 0 rows. "
        "Run: python scratch/bootstrap_eval_db.py"
    )


def test_eval_db_embedding_dimension(persistent_eval_engine):
    """Verify embeddings have the expected 384-dimensional shape (BGE-small)."""
    from pharmasense.config import EMBEDDING_DIM
    with persistent_eval_engine.connect() as conn:
        dim = conn.execute(
            text("SELECT vector_dims(embedding) FROM document_chunks LIMIT 1")
        ).scalar()
    assert dim == EMBEDDING_DIM, (
        f"Embedding dimension mismatch: expected {EMBEDDING_DIM}, got {dim}. "
        "Re-run bootstrap to regenerate with the correct model."
    )


def test_eval_db_has_jak_related_chunks(persistent_eval_engine):
    """Verify at least some chunks contain JAK-related content.

    This is the semantic precondition for S2: the vector search for
    'JAK2 cardiotoxicity' must have non-empty candidate content to retrieve.
    If this fails, the S2 query will always return 0 chunks regardless of
    similarity threshold.
    """
    with persistent_eval_engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM document_chunks WHERE chunk_text ILIKE '%jak%'")
        ).scalar()
    assert count > 0, (
        f"No JAK-related chunks found in document_chunks ({count} rows). "
        "The research_documents CSV may lack JAK content or bootstrap failed. "
        "Run: python scratch/bootstrap_eval_db.py"
    )


def test_eval_db_embedding_model_is_bge(persistent_eval_engine):
    """Verify the embedding model stored is the expected BGE model."""
    with persistent_eval_engine.connect() as conn:
        models = [r[0] for r in conn.execute(
            text("SELECT DISTINCT embedding_model FROM document_chunks")
        ).fetchall()]
    assert len(models) == 1, f"Multiple embedding models found: {models}"
    assert "bge" in models[0].lower() or "BAAI" in models[0], (
        f"Unexpected embedding model '{models[0]}'; expected BAAI/bge-small-en-v1.5"
    )
