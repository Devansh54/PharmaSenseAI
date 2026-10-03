import pytest
from unittest.mock import MagicMock
from pharmasense.llm.contracts import LLMResponse
from pharmasense.orchestration.planner import PlannerNode
from pharmasense.orchestration.state import WorkflowState

class MockLLM:
    def __init__(self, response_data):
        self.response_data = response_data
        
    def complete(self, req):
        return LLMResponse(content="", parsed=self.response_data)

def test_planner_valid_single():
    llm = MockLLM({
        "workflow_type": "single",
        "selected_specialists": ["Trial Data Analyst"],
        "task_descriptions": {"Trial Data Analyst": "Do something"},
        "resolved_entities": {}
    })
    planner = PlannerNode(llm)
    state = WorkflowState(request_id="1", user_prompt="test", plan=None, specialist_results={}, final_report=None, errors=[])
    
    res = planner(state)
    assert "errors" not in res
    assert res["plan"].workflow_type == "single"
    assert res["plan"].selected_specialists == ["Trial Data Analyst"]

def test_planner_invalid_specialist():
    llm = MockLLM({
        "workflow_type": "single",
        "selected_specialists": ["Fake Agent"],
        "task_descriptions": {},
        "resolved_entities": {}
    })
    planner = PlannerNode(llm)
    state = WorkflowState(request_id="1", user_prompt="test", plan=None, specialist_results={}, final_report=None, errors=[])
    
    res = planner(state)
    assert "errors" in res
    assert "Unauthorized specialist: Fake Agent" in res["errors"]

def test_planner_exceeds_branches():
    llm = MockLLM({
        "workflow_type": "parallel",
        "selected_specialists": ["Trial Data Analyst", "Literature Research", "Adverse Event Triage", "Compound Similarity", "Extra"],
        "task_descriptions": {},
        "resolved_entities": {}
    })
    planner = PlannerNode(llm)
    state = WorkflowState(request_id="1", user_prompt="test", plan=None, specialist_results={}, final_report=None, errors=[])
    
    res = planner(state)
    assert "errors" in res
    # Either unauthorized (Extra) or exceeded 4
    # The unauthorized check runs first
    assert "Unauthorized specialist: Extra" in res["errors"]
