import os
import json
import pytest
from unittest.mock import MagicMock
from sqlalchemy import text
from pharmasense.llm.contracts import LLMProvider, LLMRequest, LLMResponse, ToolCall
from pharmasense.llm.gateway import LLMGateway
from pharmasense.orchestration.graph import build_orchestration_graph
from pharmasense.config import GatewayConfig

class OfflineAdapter(LLMProvider):
    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self._config = GatewayConfig(model="mock-model")

    def complete(self, request: LLMRequest) -> LLMResponse:
        if self.call_count >= len(self.responses):
            return LLMResponse(content=json.dumps({"error": "Mock exhausted"}))
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp

@pytest.fixture
def run_mode():
    return os.environ.get("ACCEPTANCE_MODE", "offline")

@pytest.fixture
def acceptance_gateway(run_mode):
    if run_mode == "live":
        from pharmasense.llm.groq_adapter import GroqAdapter
        from pharmasense.config import GroqAdapterConfig
        return LLMGateway(GroqAdapter(GroqAdapterConfig()))
    return None # We will inject OfflineAdapter per test

def run_acceptance_case(gateway, session, prompt):
    graph = build_orchestration_graph(session, gateway)
    return graph.invoke({"request_id": "test_acc", "user_prompt": prompt})

def test_s1_trial_enrollment(pgvector_engine, run_mode, acceptance_gateway):
    """S1: 'Which Phase II oncology trials are below 60% enrollment right now?'"""
    if run_mode == "offline":
        responses = [
            LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="sql_query_tool", arguments={"query_id": "trial_enrollment_stats", "parameters": {"trial_phase": "Phase II", "therapeutic_area": "Oncology"}})]),
            LLMResponse(content=json.dumps({"summary": "Trials found below 60%.", "limitations": []}))
        ]
        acceptance_gateway = LLMGateway(OfflineAdapter(responses))
    
    with pgvector_engine.connect() as conn:
        state = run_acceptance_case(acceptance_gateway, conn, "Which Phase II oncology trials are below 60% enrollment right now?")
    
    assert state.get("errors", []) == []
    assert "Trial Data Analyst" in state.get("specialist_results", {})
    tools = state.get("actual_tools", [])
    if run_mode == "offline":
        assert any(t["tool_name"] == "sql_query_tool" for t in tools)

def test_s2_literature_rag(pgvector_engine, run_mode, acceptance_gateway):
    """S2: 'What has our internal research said about JAK2 inhibitors and cardiotoxicity?'"""
    if run_mode == "offline":
        responses = [
            LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="vector_search_tool", arguments={"query": "JAK2 inhibitors cardiotoxicity", "filters": {}})]),
            LLMResponse(content=json.dumps({"findings": "Internal research suggests XYZ.", "citations": ["doc1"], "search_quality": "High"}))
        ]
        acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with pgvector_engine.connect() as conn:
        state = run_acceptance_case(acceptance_gateway, conn, "What has our internal research said about JAK2 inhibitors and cardiotoxicity?")
    
    assert state.get("errors", []) == []
    assert "Literature Research" in state.get("specialist_results", {})

def test_s3_adverse_event(pgvector_engine, run_mode, acceptance_gateway):
    """S3: 'A site just reported a serious adverse event for Trial TRL-0032 — triage it.'"""
    if run_mode == "offline":
        responses = [
            LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="ae_severity_classifier_tool", arguments={"severity": "unknown", "seriousness": "serious", "adverse_event_term": "headache"})]),
            LLMResponse(content=json.dumps({"assessment": "Escalated.", "action_taken": "Escalation", "severity_assigned": "Unknown", "seriousness_assigned": "Serious", "escalated": True, "explanation": "It was serious."}))
        ]
        acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with pgvector_engine.connect() as conn:
        state = run_acceptance_case(acceptance_gateway, conn, "A site just reported a serious adverse event for Trial TRL-0032 — triage it.")
    
    assert state.get("errors", []) == []
    assert "Adverse Event Triage" in state.get("specialist_results", {})

def test_s4_compound_full_picture(pgvector_engine, run_mode, acceptance_gateway):
    """S4: 'Give me the full picture on compound DKU-1042: labs, trials, safety, and related literature.'"""
    if run_mode == "offline":
        responses = [
            # Trial
            LLMResponse(content=json.dumps({"summary": "Trial info", "limitations": []})),
            # Lit
            LLMResponse(content=json.dumps({"findings": "Lit info", "citations": [], "search_quality": "High"})),
            # AE
            LLMResponse(content=json.dumps({"assessment": "AE info", "action_taken": "None", "severity_assigned": "Unknown", "seriousness_assigned": "Unknown", "escalated": False, "explanation": "None"})),
            # Sim
            LLMResponse(content=json.dumps({"similarity_explanation": "Sim info", "similar_compounds": []})),
            # Report Writer
            LLMResponse(content=json.dumps({"report_content": "Synthesized full picture report.", "limitations_noted": [], "citations_resolved": []}))
        ]
        acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with pgvector_engine.connect() as conn:
        state = run_acceptance_case(acceptance_gateway, conn, "Give me the full picture on compound DKU-1042: labs, trials, safety, and related literature.")
    
    assert state.get("errors", []) == []
    assert "final_report" in state

def test_s5_compound_similarity(pgvector_engine, run_mode, acceptance_gateway):
    """S5: 'Find compounds similar to DKU-1042 and explain why they are considered similar.'"""
    if run_mode == "offline":
        responses = [
            LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="compound_similarity_tool", arguments={"compound_id": "DKU-1042"})]),
            LLMResponse(content=json.dumps({"similarity_explanation": "Explained.", "similar_compounds": []}))
        ]
        acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with pgvector_engine.connect() as conn:
        state = run_acceptance_case(acceptance_gateway, conn, "Find compounds similar to DKU-1042 and explain why they are considered similar.")
    
    assert state.get("errors", []) == []
    assert "Compound Similarity" in state.get("specialist_results", {})

def test_s6_report_writer(pgvector_engine, run_mode, acceptance_gateway):
    """S6: 'Summarize the findings from the trial analysis and literature research for DKU-1042.'"""
    if run_mode == "offline":
        responses = [
            LLMResponse(content=json.dumps({
                "workflow_type": "parallel",
                "selected_specialists": ["Trial Data Analyst", "Literature Research"],
                "task_descriptions": {"Trial Data Analyst": "DKU-1042", "Literature Research": "DKU-1042"},
                "resolved_entities": {}
            })),
            LLMResponse(content=json.dumps({"summary": "Trial info", "limitations": []})),
            LLMResponse(content=json.dumps({"findings": "Lit info", "citations": [], "search_quality": "High"})),
            LLMResponse(content=json.dumps({"report_content": "Synthesized full picture report.", "limitations_noted": [], "citations_resolved": []}))
        ]
        acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with pgvector_engine.connect() as conn:
        state = run_acceptance_case(acceptance_gateway, conn, "Summarize the findings from the trial analysis and literature research for DKU-1042.")
    
    assert state.get("errors", []) == []
    assert "final_report" in state

def test_s7_no_evidence(pgvector_engine, run_mode, acceptance_gateway):
    """S7: Unknown/nonexistent compound."""
    if run_mode == "offline":
        responses = [
            LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="sql_query_tool", arguments={"query_id": "compound_info", "parameters": {"compound_id": "UNKNOWN"}})]),
            LLMResponse(content=json.dumps({"summary": "No evidence found.", "limitations": []}))
        ]
        acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with pgvector_engine.connect() as conn:
        state = run_acceptance_case(acceptance_gateway, conn, "What clinical trials involve compound UNKNOWN-999?")
    
    assert state.get("errors", []) == []
    assert "Trial Data Analyst" in state.get("specialist_results", {})

def test_s8_medical_advice(pgvector_engine, run_mode, acceptance_gateway):
    """S8: 'What medication should a patient take for chest pain?'"""
    if run_mode == "offline":
        adp = OfflineAdapter([])
        acceptance_gateway = LLMGateway(adp)

    with pgvector_engine.connect() as conn:
        state = run_acceptance_case(acceptance_gateway, conn, "What medication should a patient take for chest pain?")
    
    assert state.get("errors") != []
    assert "Guardrail blocked request" in state.get("errors")[0]
    
    if run_mode == "offline":
        assert adp.call_count == 0
