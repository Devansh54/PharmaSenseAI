import os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pharmasense.config import DATABASE_URL
from pharmasense.tools.sql_query import sql_query_tool, SqlQueryInput

def test_trials_by_compound():
    db_url = os.environ.get("EVAL_DATABASE_URL", DATABASE_URL)
    engine = create_engine(db_url)
    with Session(engine) as session:
        # 1. Query by compound name (DKU-1001)
        input_name = SqlQueryInput(
            query_id="trials_by_compound",
            parameters={"compound_id": "DKU-1001"}
        )
        out_name = sql_query_tool(session, input_name)
        
        assert out_name.error is None
        assert len(out_name.results) == 1
        assert out_name.results[0]["trial_id"] == "TRL-0001"
        
        # 2. Query by canonical ID (CMP-0002)
        input_id = SqlQueryInput(
            query_id="trials_by_compound",
            parameters={"compound_id": "CMP-0002"}
        )
        out_id = sql_query_tool(session, input_id)
        
        assert out_id.error is None
        assert len(out_id.results) == 1
        assert out_id.results[0]["trial_id"] == "TRL-0001"
