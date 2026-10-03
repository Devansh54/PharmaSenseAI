"""Integration tests for transactional ingestion.

These require a reachable PostgreSQL instance (provided as a service in
CI). They are skipped automatically otherwise so the rest of the suite
can still run without a database.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from pharmasense.db.source_schema import Base
from pharmasense.data.ingest.import_csvs import import_all_csvs
from pharmasense.data.ingest.drift import detect_drift

DATABASE_URL = os.environ.get(
    "PHARMASENSE_TEST_DATABASE_URL",
    "postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense_test"
)

def _ensure_test_db():
    base_url = "postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense"
    db_name = "pharmasense_test"
    from sqlalchemy import create_engine, text
    eng = create_engine(base_url, isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {db_name}"))
    except Exception:
        pass


def _engine_or_skip():
    _ensure_test_db()
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip(f"No reachable PostgreSQL instance at {DATABASE_URL}; skipping ingestion tests.")
    return engine


@pytest.fixture()
def engine():
    eng = _engine_or_skip()
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


def test_import_all_csvs_loads_expected_row_counts(engine):
    result = import_all_csvs(engine)
    assert result["tables_loaded"]["compounds"] == 150
    assert result["tables_loaded"]["clinical_trials"] == 110
    assert result["tables_loaded"]["trial_sites"] == 375
    assert result["tables_loaded"]["lab_results"] == 2000
    assert result["tables_loaded"]["adverse_events"] == 500
    assert result["tables_loaded"]["research_documents"] == 250
    assert result["tables_loaded"]["agent_interaction_logs"] == 400


def test_repeated_import_is_idempotent(engine):
    first = import_all_csvs(engine)
    second = import_all_csvs(engine)
    assert first["tables_loaded"] == second["tables_loaded"]


def test_drift_detection_reports_no_drift_after_reimport(engine):
    import_all_csvs(engine)
    drift = detect_drift()
    assert drift["baseline_exists"] is True
    assert drift["drift_detected"] is False
