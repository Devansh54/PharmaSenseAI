"""Tests for SQL query tool."""
import pytest
from sqlalchemy.orm import Session
from pharmasense.tools.sql_query import sql_query_tool, SqlQueryInput
from pharmasense.db.source_schema import ClinicalTrial, Compound

def test_sql_query_unknown_query(pgvector_engine):
    with Session(pgvector_engine) as session:
        result = sql_query_tool(session, SqlQueryInput(query_id="invalid", parameters={}))
        assert result.error == "Unknown query_id: invalid"

def test_sql_query_trial_summary(pgvector_engine):
    with Session(pgvector_engine) as session:
        # Insert a compound and trial
        cmp = Compound(compound_id="CMP-101")
        session.add(cmp)
        session.flush()
        trial = ClinicalTrial(trial_id="TRIAL-101", compound_id="CMP-101", trial_phase="Phase II", target_enrollment=500)
        session.add(trial)
        session.commit()
        
        result = sql_query_tool(session, SqlQueryInput(query_id="trial_summary", parameters={"trial_id": "TRIAL-101"}))
        assert not result.error
        assert len(result.results) == 1
        row = result.results[0]
        assert row["trial_phase"] == "Phase II"
        assert row["target_enrollment"] == 500
