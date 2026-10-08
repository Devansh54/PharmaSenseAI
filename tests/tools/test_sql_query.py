"""Tests for SQL query tool."""
import pytest
from sqlalchemy.orm import Session
from pharmasense.tools.sql_query import sql_query_tool, SqlQueryInput
from pharmasense.db.source_schema import ClinicalTrial, Compound

def test_sql_query_unknown_query(pgvector_engine):
    with Session(pgvector_engine) as session:
        from pydantic import ValidationError
        try:
            sql_query_tool(session, SqlQueryInput(query_id="invalid", parameters={}))
            assert False, "Should have raised ValidationError"
        except ValidationError:
            pass

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

def test_sql_query_sites_by_trial_attributes(pgvector_engine):
    with Session(pgvector_engine) as session:
        from pharmasense.db.source_schema import TrialSite
        
        cmp = Compound(compound_id="CMP-102")
        session.add(cmp)
        session.flush()
        
        t1 = ClinicalTrial(trial_id="TRIAL-102", compound_id="CMP-102", trial_phase="Phase II", therapeutic_area="Oncology")
        t2 = ClinicalTrial(trial_id="TRIAL-103", compound_id="CMP-102", trial_phase="Phase III", therapeutic_area="Oncology")
        session.add_all([t1, t2])
        session.flush()
        
        s1 = TrialSite(site_id="SITE-1", trial_id="TRIAL-102", site_name="Oncology Center", country="USA", enrollment_count=10, site_status="Active")
        s2 = TrialSite(site_id="SITE-2", trial_id="TRIAL-103", site_name="Other Center", country="UK", enrollment_count=20, site_status="Active")
        session.add_all([s1, s2])
        session.commit()
        
        result = sql_query_tool(session, SqlQueryInput(
            query_id="sites_by_trial_attributes", 
            parameters={"trial_phase": "Phase II", "therapeutic_area": "Oncology"}
        ))
        
        assert not result.error
        assert len(result.results) == 1
        row = result.results[0]
        assert row["site_name"] == "Oncology Center"
        assert row["country"] == "USA"
        assert row["enrollment_count"] == 10
        assert row["site_status"] == "Active"
        assert row["trial_phase"] == "Phase II"
        assert row["therapeutic_area"] == "Oncology"

def test_sql_query_all_compounds(pgvector_engine):
    with Session(pgvector_engine) as session:
        cmp1 = Compound(compound_id="CMP-ALL-1", compound_name="Comp 1", chemical_class="Class A")
        cmp2 = Compound(compound_id="CMP-ALL-2", compound_name="Comp 2", chemical_class="Class B")
        session.add_all([cmp1, cmp2])
        session.commit()
        
        result = sql_query_tool(session, SqlQueryInput(
            query_id="all_compounds", 
            parameters={}
        ))
        
        assert not result.error
        # Could be more than 2 if other tests inserted compounds without rollback,
        # but we know it should at least return cmp1 and cmp2
        ids = [r["compound_id"] for r in result.results]
        assert "CMP-ALL-1" in ids
        assert "CMP-ALL-2" in ids
