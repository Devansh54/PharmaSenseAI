import pytest
from unittest.mock import MagicMock
from pharmasense.orchestration.graph import build_orchestration_graph
from pharmasense.orchestration.state import Plan

# Mock the actual agents
import pharmasense.orchestration.graph as graph_module

def test_single_workflow():
    session = MagicMock()
    llm = MagicMock()
    
    # Mock Planner LLM call to return a single workflow plan
    llm.complete.return_value.parsed = {
        "workflow_type": "single",
        "selected_specialists": ["Trial Data Analyst"],
        "task_descriptions": {"Trial Data Analyst": "Test"},
        "resolved_entities": {}
    }
    
    # We must patch the agents so they don't actually call LLM during test
    mock_agent = MagicMock()
    mock_agent.run.return_value.model_dump.return_value = {"summary": "trial summary", "limitations": []}
    
    # Temporarily monkeypatch the factory
    original_factory = graph_module.create_trial_data_analyst
    graph_module.create_trial_data_analyst = lambda s, l: mock_agent
    
    try:
        app = build_orchestration_graph(session, llm)
        final_state = app.invoke({"request_id": "1", "user_prompt": "test"})
        
        assert "errors" not in final_state or not final_state["errors"]
        assert "Trial Data Analyst" in final_state["specialist_results"]
        # In single workflow, report writer should not run
        assert final_state.get("final_report") is None
    finally:
        graph_module.create_trial_data_analyst = original_factory

def test_parallel_workflow():
    session = MagicMock()
    llm = MagicMock()
    
    llm.complete.return_value.parsed = {
        "workflow_type": "parallel",
        "selected_specialists": ["Trial Data Analyst", "Literature Research"],
        "task_descriptions": {"Trial Data Analyst": "t", "Literature Research": "l"},
        "resolved_entities": {}
    }
    
    mock_trial_agent = MagicMock()
    mock_trial_agent.run.return_value.model_dump.return_value = {"summary": "trial", "limitations": []}
    
    mock_lit_agent = MagicMock()
    mock_lit_agent.run.return_value.model_dump.return_value = {"findings": "lit", "citations": [], "no_evidence_found": False}
    
    mock_report = MagicMock()
    mock_report.run.return_value.model_dump.return_value = {"report_text": "final", "limitations_noted": [], "citations_resolved": []}
    
    orig_t = graph_module.create_trial_data_analyst
    orig_l = graph_module.create_literature_research_agent
    orig_r = graph_module.create_report_writer_agent
    
    graph_module.create_trial_data_analyst = lambda s, l: mock_trial_agent
    graph_module.create_literature_research_agent = lambda s, l: mock_lit_agent
    graph_module.create_report_writer_agent = lambda s, l: mock_report
    
    try:
        app = build_orchestration_graph(session, llm)
        final_state = app.invoke({"request_id": "2", "user_prompt": "test parallel"})
        
        assert "Trial Data Analyst" in final_state["specialist_results"]
        assert "Literature Research" in final_state["specialist_results"]
        assert final_state["final_report"]["report_text"] == "final"
    finally:
        graph_module.create_trial_data_analyst = orig_t
        graph_module.create_literature_research_agent = orig_l
        graph_module.create_report_writer_agent = orig_r

def test_sequential_workflow():
    session = MagicMock()
    llm = MagicMock()
    
    llm.complete.return_value.parsed = {
        "workflow_type": "sequential",
        "selected_specialists": ["Trial Data Analyst"],
        "task_descriptions": {"Trial Data Analyst": "t"},
        "resolved_entities": {}
    }
    
    mock_trial = MagicMock()
    mock_trial.run.return_value.model_dump.return_value = {"summary": "trial", "limitations": []}
    
    mock_report = MagicMock()
    mock_report.run.return_value.model_dump.return_value = {"report_text": "final", "limitations_noted": [], "citations_resolved": []}
    
    orig_t = graph_module.create_trial_data_analyst
    orig_r = graph_module.create_report_writer_agent
    
    graph_module.create_trial_data_analyst = lambda s, l: mock_trial
    graph_module.create_report_writer_agent = lambda s, l: mock_report
    
    try:
        app = build_orchestration_graph(session, llm)
        final_state = app.invoke({"request_id": "3", "user_prompt": "test seq"})
        
        assert "Trial Data Analyst" in final_state["specialist_results"]
        assert "final_report" in final_state
        assert final_state["final_report"]["report_text"] == "final"
    finally:
        graph_module.create_trial_data_analyst = orig_t
        graph_module.create_report_writer_agent = orig_r
