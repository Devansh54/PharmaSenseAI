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

def test_planner_deterministic_q1():
    llm = MockLLM({})
    planner = PlannerNode(llm)
    state = WorkflowState(request_id="1", user_prompt="Which Phase II oncology trials are below 60% enrollment right now?", plan=None, specialist_results={}, final_report=None, errors=[])
    
    res = planner(state)
    assert "errors" not in res
    plan = res["plan"]
    assert plan.workflow_type == "single"
    assert plan.selected_specialists == ["Trial Data Analyst"]

def test_planner_deterministic_q3():
    llm = MockLLM({})
    planner = PlannerNode(llm)
    state = WorkflowState(request_id="1", user_prompt="What sites are associated with Phase II oncology trials, and how many participants have been enrolled at those sites?", plan=None, specialist_results={}, final_report=None, errors=[])
    
    res = planner(state)
    assert "errors" not in res
    plan = res["plan"]
    assert plan.workflow_type == "single"
    assert plan.selected_specialists == ["Trial Data Analyst"]
    assert "sites_by_trial_attributes" in plan.task_descriptions["Trial Data Analyst"]
    assert "MUST use the `sites_by_trial_attributes`" in plan.task_descriptions["Trial Data Analyst"]

def test_planner_routing_matrix():
    cases = [
        ("Which Phase II oncology trials are below 60% enrollment right now?", ["Trial Data Analyst"]),
        ("What is the Phase II oncology enrollment status?", ["Trial Data Analyst"]),
        ("What are the trial sites and participants for TRL-0001?", ["Trial Data Analyst"]),
        ("Find JAK2 and cardiotoxicity literature.", ["Literature Research"]),
        ("Is there any evidence for unknown compound ZXQ-9999?", ["Literature Research"]),
        ("List the serious adverse events in TRL-0034.", ["Adverse Event Triage"]),
        ("What is the compound similarity for VLX-1000?", ["Compound Similarity"]),
        ("What are the laboratory findings for VLX-1000?", ["Trial Data Analyst"]),
        ("Please provide a trial and research synthesis for DKU-1001.", ["Trial Data Analyst", "Literature Research"]),
        ("I have chest pain, what medication should I take?", [])
    ]
    
    llm = MockLLM({})
    planner = PlannerNode(llm)
    
    for prompt, expected_specialists in cases:
        state = WorkflowState(request_id="1", user_prompt=prompt, plan=None, specialist_results={}, final_report=None, errors=[])
        res = planner(state)
        
        if len(expected_specialists) == 0:
            # Case 10 returns an error with empty specialists
            assert "errors" in res
            assert res["errors"] == ["Out-of-scope request blocked."]
        else:
            assert "errors" not in res
            plan = res["plan"]
            assert sorted(plan.selected_specialists) == sorted(expected_specialists)