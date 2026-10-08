import os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pharmasense.config import DATABASE_URL
from pharmasense.tools.sql_query import sql_query_tool, SqlQueryInput
from pharmasense.tools.compound_similarity import compound_similarity_tool, CompoundSimilarityInput

def test_q7_similarity_offline():
    db_url = os.environ.get("EVAL_DATABASE_URL", DATABASE_URL)
    engine = create_engine(db_url)
    with Session(engine) as session:
        # Get VLX-1000 (CMP-0001) info
        vlx_input = SqlQueryInput(query_id="compound_info", parameters={"compound_id": "CMP-0001"})
        vlx_out = sql_query_tool(session, vlx_input)
        assert not vlx_out.error
        
        sim_input = CompoundSimilarityInput(
            target_compound_id="CMP-0001",
            top_k=5
        )
        sim_out = compound_similarity_tool(session, sim_input)
        
        assert len(sim_out.top_candidates) > 0, "No similarity candidates found, but expected some!"
        
        best = sim_out.top_candidates[0]
        assert best.overall_score > 0.5, f"Best candidate score too low: {best.overall_score}"
        assert best.coverage == 1.0, f"Coverage should be 1.0, got {best.coverage}"

if __name__ == "__main__":
    test_q7_similarity_offline()
    print("Test passed! Similarity returned candidates.")
