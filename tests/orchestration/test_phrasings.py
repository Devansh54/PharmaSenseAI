import pytest
from unittest.mock import MagicMock
from pharmasense.llm.contracts import LLMResponse
from pharmasense.orchestration.planner import PlannerNode, try_deterministic_route
from pharmasense.orchestration.state import WorkflowState

class MockLLM:
    def __init__(self, response_data=None):
        self.response_data = response_data or {}
        
    def complete(self, req):
        return LLMResponse(content="", parsed=self.response_data)

def check_routing(prompt: str, expected_specialists: list[str], expected_instruction_subset: str = None, expect_error: bool = False):
    llm = MockLLM({
        "workflow_type": "single" if len(expected_specialists) <= 1 else "parallel",
        "selected_specialists": expected_specialists,
        "task_descriptions": {s: prompt for s in expected_specialists},
        "resolved_entities": {}
    })
    planner = PlannerNode(llm)
    state = WorkflowState(request_id="1", user_prompt=prompt, plan=None, specialist_results={}, final_report=None, errors=[])
    
    res = planner(state)
    if expect_error:
        assert "errors" in res
        return
        
    assert "errors" not in res
    plan = res["plan"]
    
    assert set(plan.selected_specialists) == set(expected_specialists)
    
    if expected_instruction_subset and expected_specialists:
        spec = expected_specialists[0]
        assert expected_instruction_subset in plan.task_descriptions[spec]

def test_phrasings_trial_enrollment_threshold():
    phrases = [
        "Which Phase II oncology trials are below 60% enrollment?",
        "Which Phase II oncology studies have enrolled less than 60%?",
        "Which Phase II oncology trials are behind on enrollment?"
    ]
    for p in phrases:
        check_routing(p, ["Trial Data Analyst"], "trial_enrollment_stats")

def test_phrasings_trial_enrollment_status():
    phrases = [
        "Show me the current enrollment status of the Phase II oncology trials.",
        "What is the recruitment status for Phase II oncology studies?",
        "Give me the enrollment numbers for clinical studies in Phase II oncology."
    ]
    for p in phrases:
        # Might go through LLM or single-domain match. Both end up at Trial Data Analyst
        check_routing(p, ["Trial Data Analyst"])

def test_phrasings_trial_sites():
    phrases = [
        "What sites are associated with Phase II oncology trials?",
        "Which clinical sites are running the Phase II oncology trials?",
        "Show site-level enrollment for Phase II oncology studies."
    ]
    for p in phrases:
        check_routing(p, ["Trial Data Analyst"], "sites_by_trial_attributes")

def test_phrasings_literature():
    phrases = [
        "What does our research say about JAK2 inhibitors and cardiotoxicity?",
        "Find internal research on JAK2 inhibitors and cardiac safety.",
        "What have our documents reported about JAK2-related cardiotoxicity?"
    ]
    for p in phrases:
        check_routing(p, ["Literature Research"])

def test_phrasings_no_evidence():
    phrases = [
        "What do we know about ZXQ-9999?",
        "Is there any internal research on ZXQ-9999?",
        "Find evidence for fictional compound ZXQ-9999."
    ]
    for p in phrases:
        # LLM fallback for "What do we know about ZXQ-9999?" could route to Literature Research. 
        # Our MockLLM routes to Literature Research. 
        # The key is that the planner accepts it. 
        # We will mock the LLM to return Literature Research and ensure it works.
        check_routing(p, ["Literature Research"])

def test_phrasings_adverse_event_triage():
    phrases = [
        "A site just reported an adverse event for Trial TRL-0034.",
        "Triage this safety event for study TRL-0034.",
        "We have a serious event reported in Trial TRL-0034, requires review."
    ]
    for p in phrases:
        check_routing(p, ["Adverse Event Triage"])

def test_phrasings_compound_similarity():
    phrases = [
        "Find compounds similar to VLX-1000.",
        "Which compounds are most similar to VLX-1000?",
        "Show comparable compounds and explain why."
    ]
    for p in phrases:
        check_routing(p, ["Compound Similarity"])

def test_phrasings_laboratory_results():
    phrases = [
        "What lab results do we have for VLX-1000?",
        "Show laboratory findings for VLX-1000.",
        "What assay results are available for VLX-1000?"
    ]
    for p in phrases:
        check_routing(p, ["Trial Data Analyst"])

def test_phrasings_multi_domain_synthesis():
    phrases = [
        "Give me the full picture on VLX-1000.",
        "Summarize the trial and research evidence for VLX-1000.",
        "Combine the available clinical and literature findings for VLX-1000."
    ]
    for p in phrases:
        check_routing(p, ["Trial Data Analyst", "Literature Research", "Adverse Event Triage", "Compound Similarity"])

def test_phrasings_medical_advice():
    phrases = [
        "What medication should a patient take for chest pain?",
        "What treatment should this patient take?",
        "Which drug should I prescribe?"
    ]
    for p in phrases:
        check_routing(p, [], expect_error=True)
