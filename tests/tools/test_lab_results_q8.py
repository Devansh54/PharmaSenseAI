import os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pharmasense.config import DATABASE_URL
from pharmasense.tools.sql_query import sql_query_tool, SqlQueryInput

def test_q8_lab_results_name_resolution():
    """
    Focused offline regression test for Q8.
    Verifies that querying lab_results_summary by compound_name (VLX-1000)
    correctly resolves to compound_id (CMP-0001) and returns exactly 15 records.
    """
    db_url = os.environ.get("EVAL_DATABASE_URL", DATABASE_URL)
    engine = create_engine(db_url)
    with Session(engine) as session:
        # Test 1: Query by compound name
        name_input = SqlQueryInput(
            query_id="lab_results_summary",
            parameters={"compound_id": "VLX-1000"}
        )
        name_out = sql_query_tool(session, name_input)
        
        assert not name_out.error
        assert len(name_out.results) == 15
        
        # Test 2: Query by compound ID to ensure identical behavior
        id_input = SqlQueryInput(
            query_id="lab_results_summary",
            parameters={"compound_id": "CMP-0001"}
        )
        id_out = sql_query_tool(session, id_input)
        
        assert not id_out.error
        assert len(id_out.results) == 15
