import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pharmasense.config import DATABASE_URL
from pharmasense.orchestration.graph import build_orchestration_graph
from pharmasense.orchestration.state import WorkflowState
from pharmasense.llm.contracts import LLMProvider, LLMResponse, LLMRequest, Message

class MockLLM(LLMProvider):
    def __init__(self):
        self.call_count = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        messages_text = str(request.messages)
        
        # 1. Mock Planner
        if "You are the Router/Planner." in messages_text:
            return LLMResponse(
                content="",
                tool_calls=[],
                parsed={
                    "workflow_type": "sequential",
                    "selected_specialists": ["Compound Similarity"],
                    "task_descriptions": {"Compound Similarity": "Find compounds similar to VLX-1000"},
                    "resolved_entities": {}
                }
            )
            
        # 2. Mock Compound Similarity Agent - iteration 1
        if "You are the Compound Similarity specialist." in messages_text and self.call_count == 2:
            from pharmasense.llm.contracts import ToolCall
            return LLMResponse(
                content="I need to fetch compound info.",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="sql_query_tool",
                        arguments={"query_id": "compound_info", "parameters": {"compound_id": "CMP-0001"}}
                    ),
                    ToolCall(
                        id="call_2",
                        name="sql_query_tool",
                        arguments={"query_id": "compound_info", "parameters": {"compound_id": "CMP-0133"}}
                    )
                ]
            )

        # 3. Mock Compound Similarity Agent - iteration 2
        if "You are the Compound Similarity specialist." in messages_text and self.call_count == 3:
            from pharmasense.llm.contracts import ToolCall
            # Now we call the similarity tool
            return LLMResponse(
                content="I will compare them.",
                tool_calls=[
                    ToolCall(
                        id="call_3",
                        name="compound_similarity_tool",
                        arguments={
                            "compound_1_attrs": {"compound_id": "CMP-0001", "chemical_class": "Peptide", "target_protein": "JAK2", "therapeutic_area": "Neurology", "molecular_weight_da": 1387.41, "solubility_mg_ml": 3.292, "toxicity_score": 0.085},
                            "compound_2_attrs": {"compound_id": "CMP-0133", "chemical_class": "Peptide", "target_protein": "JAK2", "therapeutic_area": "Infectious Disease", "molecular_weight_da": 1342.67, "solubility_mg_ml": 0.086, "toxicity_score": 0.223}
                        }
                    )
                ]
            )
            
        # 4. Mock Compound Similarity Agent - iteration 3 (finalizing output)
        if "You are the Compound Similarity specialist." in messages_text and self.call_count == 4:
            return LLMResponse(
                content="",
                tool_calls=[],
                parsed={
                    "score": 0.563,
                    "explanation": "CMP-0133 is highly similar to VLX-1000.",
                    "coverage": 1.0
                }
            )
            
        # 5. Mock Report Writer
        if "Synthesize the following findings into a final report:" in messages_text:
            return LLMResponse(
                content="",
                tool_calls=[],
                parsed={
                    "report_text": "CMP-0133 is highly similar to VLX-1000 with a score of 0.563."
                }
            )
            
        # 6. Mock Evidence Validator
        if "You are an evidence validation judge." in messages_text:
            return LLMResponse(
                content="",
                tool_calls=[],
                parsed={
                    "is_supported": True,
                    "reason": "The context supports the claim that CMP-0133 is similar."
                }
            )
            
        return LLMResponse(content="Unexpected call", tool_calls=[], parsed={})

def test_q7_e2e_offline():
    db_url = os.environ.get("EVAL_DATABASE_URL", DATABASE_URL)
    engine = create_engine(db_url)
    llm = MockLLM()
    
    with Session(engine) as session:
        graph = build_orchestration_graph(session, llm)
        state = {
            "request_id": "test-q7-e2e",
            "session_id": "test",
            "user_prompt": "Find compounds similar to VLX-1000 and explain why they are considered similar.",
            "plan": None,
            "specialist_results": {},
            "errors": [],
            "actual_tools": [],
            "final_report": None
        }
        
        result = graph.invoke(state)
        assert result.get("errors") == [], f"Expected no errors, got {result.get('errors')}"
        assert result.get("final_report") is not None
        assert "CMP-0133" in result["final_report"]["report_text"]

if __name__ == "__main__":
    test_q7_e2e_offline()
