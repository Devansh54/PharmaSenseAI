"""Shared pytest fixtures for Phase 1/2/3 tests."""
import os
import sys
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pharmasense.config import CSV_FILES
from pharmasense.contracts import LOAD_ORDER

_PHASE3_DATABASE_URL = os.environ.get(
    "PHARMASENSE_TEST_DATABASE_URL",
    os.environ.get(
        "PHARMASENSE_DATABASE_URL",
        "postgresql+psycopg2://localhost:5432/pharmasense",
    ),
)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "smoke: live tests that call a real external provider (skipped without credentials)"
    )


@pytest.fixture(scope="session")
def csv_frames():
    return {
        name: pd.read_csv(CSV_FILES[name], dtype=str, keep_default_na=False)
        for name in LOAD_ORDER
    }


@pytest.fixture()
def pgvector_engine():
    """A Postgres engine with pgvector enabled and all tables created.

    Mirrors tests/test_ingestion.py's `engine` fixture for Phase 1:
    skipped automatically when no PostgreSQL instance is reachable, so
    the rest of the suite still runs without a database.
    """
    from pharmasense.db.source_schema import Base
    import pharmasense.db.models  # noqa: F401 - registers document_chunks on Base.metadata

    engine = create_engine(_PHASE3_DATABASE_URL)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip(f"No reachable PostgreSQL instance at {_PHASE3_DATABASE_URL}; skipping pgvector tests.")

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
