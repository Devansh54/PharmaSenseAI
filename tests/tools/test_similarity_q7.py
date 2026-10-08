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
        vlx_attrs = vlx_out.results[0]
        
        # Get all compounds
        all_input = SqlQueryInput(query_id="all_compounds", parameters={})
        all_out = sql_query_tool(session, all_input)
        assert not all_out.error
        
        candidates = []
        for c in all_out.results:
            if c["compound_id"] == "CMP-0001":
                continue
            
            sim_input = CompoundSimilarityInput(
                compound_1_attrs=vlx_attrs,
                compound_2_attrs=c
            )
            sim_out = compound_similarity_tool(sim_input)
            
            if sim_out.overall_score > 0.0: # Even minor similarity
                candidates.append((c["compound_id"], sim_out.overall_score, sim_out.coverage))
                
        # Sort candidates by score
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Verify that we actually found candidates
        assert len(candidates) > 0, "No similarity candidates found, but expected some!"
        
        # The best candidate should have a reasonable score
        best = candidates[0]
        assert best[1] > 0.5, f"Best candidate score too low: {best[1]}"
        assert best[2] == 1.0, f"Coverage should be 1.0, got {best[2]}"

if __name__ == "__main__":
    test_q7_similarity_offline()
    print("Test passed! Similarity returned candidates.")
