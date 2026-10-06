import os
import json
import pytest
from unittest.mock import MagicMock
from sqlalchemy import text
from sqlalchemy.orm import Session
from pharmasense.llm.contracts import LLMProvider, LLMRequest, LLMResponse, ToolCall, Usage
from pharmasense.llm.gateway import LLMGateway
from pharmasense.llm.budget import BudgetEnforcingGateway, LLMBudgetExceededError, RunBudget
from pharmasense.orchestration.graph import build_orchestration_graph
from pharmasense.config import GatewayConfig

class OfflineAdapter(LLMProvider):
    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self.call_requests = []
        self._config = GatewayConfig(model="mock-model")

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_requests.append(request)
        # Simple heuristic to match schema to response
        schema_str = json.dumps(request.response_schema) if request.response_schema else ""
        prompt_str = str(request.messages)

        # Determine expected type based on schema or prompt
        for r in self.responses:
            if not getattr(r, "_used", False):
                content = r.content or ""
                # Tool calls
                if r.tool_calls:
                    r._used = True
                    return r
                # Match by content keys
                if "is_supported" in content and "is_supported" in schema_str:
                    r._used = True
                    return r
                if "report_text" in content and "report_text" in schema_str:
                    r._used = True
                    return r
                if "score" in content and "score" in schema_str:
                    r._used = True
                    return r
                if "findings" in content and "findings" in schema_str:
                    r._used = True
                    return r
                if "final_severity" in content and "final_severity" in schema_str:
                    r._used = True
                    return r
                if "summary" in content and "summary" in schema_str:
                    r._used = True
                    return r
                if "workflow_type" in content and "workflow_type" in schema_str:
                    r._used = True
                    return r

        # Fallback if no schema matches
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp

        return LLMResponse(content=json.dumps({"error": "Mock exhausted"}))

@pytest.fixture
def run_mode():
    return os.environ.get("ACCEPTANCE_MODE", "offline")

# Default budget for live acceptance runs.  Generous enough for all
# current cases (S4 multi-specialist fan-out uses ~6-12 LLM calls);
# tight enough to abort runaway loops before Groq daily quota is hit.
_LIVE_RUN_BUDGET = RunBudget(
    max_llm_calls=int(os.environ.get("ACCEPTANCE_MAX_LLM_CALLS", "40")),
    max_prompt_tokens=int(os.environ.get("ACCEPTANCE_MAX_PROMPT_TOKENS", "80000")),
    max_completion_tokens=int(os.environ.get("ACCEPTANCE_MAX_COMPLETION_TOKENS", "20000")),
)

@pytest.fixture
def acceptance_gateway(run_mode):
    if run_mode == "live":
        from pharmasense.llm.groq_adapter import GroqAdapter
        from pharmasense.config import GroqAdapterConfig
        inner = LLMGateway(GroqAdapter(GroqAdapterConfig()))
        return BudgetEnforcingGateway(inner=inner, budget=_LIVE_RUN_BUDGET)
    return None  # We will inject OfflineAdapter per test

def get_acceptance_db_engine_generator(run_mode, pgvector_engine):
    if run_mode == "live":
        from sqlalchemy import create_engine
        eval_url = os.environ.get("EVAL_DATABASE_URL")
        if not eval_url:
            pytest.fail("EVAL_DATABASE_URL must be set for live acceptance tests.")
        engine = create_engine(eval_url)
        yield engine
        engine.dispose()
    else:
        yield pgvector_engine

@pytest.fixture
def acceptance_db_engine(run_mode, pgvector_engine):
    yield from get_acceptance_db_engine_generator(run_mode, pgvector_engine)



def run_acceptance_case(gateway, session, prompt):
    graph = build_orchestration_graph(session, gateway)
    return graph.invoke({"request_id": "test_acc", "user_prompt": prompt})

def test_s1_trial_enrollment(acceptance_db_engine, run_mode, acceptance_gateway):
    """S1: 'Which Phase II oncology trials are below 60% enrollment right now?'"""
    if run_mode == "offline":
        responses = [
            LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="sql_query_tool", arguments={"query_id": "trial_enrollment_stats", "parameters": {"trial_phase": "Phase II", "therapeutic_area": "Oncology"}})]),
            LLMResponse(content=json.dumps({"summary": "Trials found below 60%.", "limitations": []})),
            LLMResponse(content=json.dumps({"is_supported": True, "reason": "Yes"}))
        ]
        adapter = OfflineAdapter(responses)
        acceptance_gateway = LLMGateway(adapter)

    with Session(acceptance_db_engine) as session:
        state = run_acceptance_case(acceptance_gateway, session, "Which Phase II oncology trials are below 60% enrollment right now?")

    assert state.get("errors", []) == []
    assert "Trial Data Analyst" in state.get("specialist_results", {})
    tools = state.get("actual_tools", [])
    if run_mode == "offline":
        assert any(t["tool_name"] == "sql_query_tool" for t in tools)
        assert len(tools) == 1  # exactly one execution

        reqs = adapter.call_requests
        assert len(reqs) == 2 # TrialAgent tool call, TrialAgent final (OutputGuardrail is deterministic)
        assert reqs[0].tools is not None
        assert reqs[1].tools is None
        assert reqs[1].tool_choice == "none"
        assert reqs[1].response_schema is not None

    # Deterministic factual correctness assertions against authoritative SQL result
    sql_exec = next(t for t in tools if t["tool_name"] == "sql_query_tool")
    sql_results = sql_exec.get("result", {}).get("results", [])
    report_text = state.get("final_report", {}).get("report_content", "")

    below_60 = [r for r in sql_results if r.get("is_below_threshold") is True]
    above_60 = [r for r in sql_results if r.get("is_below_threshold") is False]

    for trial in below_60:
        assert trial["trial_id"] in report_text, f"Below-60% trial {trial['trial_id']} was omitted from the report."

    for trial in above_60:
        # If it mentions an above_60 trial, it better not claim it's below 60 or meets/exceeds incorrectly?
        # The prompt says: "every omitted Phase II oncology trial is actually at/above 60%"
        # (This is logically checked by ensuring all below_60 are NOT omitted, which we just did above).
        pass

    # Ensure the model didn't make the exact mathematical hallucination observed
    assert "35.6% exceeds 60%" not in report_text
    assert "35.6% meets or exceeds 60%" not in report_text

def test_s1_factual_correctness_regression(acceptance_db_engine, run_mode, acceptance_gateway):
    """Regression test: LLM falsely claims 35.6% meets/exceeds 60%. Output Guardrail should catch it or test should fail."""
    if run_mode == "live":
        pytest.skip("Regression test is offline-only")

    # Authoritative tool result has TRL-0037 with enrollment 35.6% and is_below_threshold = True
    responses = [
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="sql_query_tool", arguments={"query_id": "trial_enrollment_stats", "parameters": {"trial_phase": "Phase II", "therapeutic_area": "Oncology", "threshold_pct": 60.0}})]),
        # Simulated hallucinated response
        LLMResponse(content=json.dumps({"summary": "TRL-0037 meets or exceeds 60%.", "limitations": []})),
        # Guardrail should technically fail if it correctly evaluates evidence
        LLMResponse(content=json.dumps({"is_supported": False, "reason": "TRL-0037 is actually below 60% based on the data."}))
    ]
    acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with acceptance_db_engine.begin() as conn:
        conn.execute(text("INSERT INTO compounds (compound_id, compound_name) VALUES ('C-01', 'Test Compound') ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO clinical_trials (trial_id, compound_id, trial_phase, therapeutic_area, status, target_enrollment) VALUES ('TRL-0037', 'C-01', 'Phase II', 'Oncology', 'Active', 100) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO trial_sites (site_id, trial_id, site_name, country, enrollment_count, site_status) VALUES ('S-01', 'TRL-0037', 'Site', 'US', 35, 'Active') ON CONFLICT DO NOTHING"))

    with Session(acceptance_db_engine) as session:
        state = run_acceptance_case(acceptance_gateway, session, "Which Phase II oncology trials are below 60% enrollment right now?")

    # If the guardrail successfully caught the hallucination, state should contain an error or the guardrail failed the report.
    # The output guardrail will fail if is_supported is false.
    assert state.get("errors") != []
    assert any("Evidence validation failed" in err for err in state.get("errors", []))

def test_s1_factual_correctness_false_positive_regression(acceptance_db_engine, run_mode, acceptance_gateway):
    """Regression test: LLM correctly separates below-threshold and above-threshold trials. Output Guardrail should NOT falsely reject it."""
    if run_mode == "live":
        pytest.skip("Regression test is offline-only")

    # Authoritative tool result has TRL-0019 and TRL-0037 as below threshold
    responses = [
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="sql_query_tool", arguments={"query_id": "trial_enrollment_stats", "parameters": {"trial_phase": "Phase II", "therapeutic_area": "Oncology", "threshold_pct": 60.0}})]),
        # Simulated correct response with 'above the threshold' explicitly mentioned
        LLMResponse(content=json.dumps({"summary": "Two Phase II oncology trials are currently below the 60% enrollment threshold: TRL-0019 (Recruiting, 59.34% enrolled) and TRL-0037 (Active, not recruiting, 35.69% enrolled). Trials TRL-0010, TRL-0077, and TRL-0087 are at or above the threshold and are excluded from this finding.", "limitations": []}))
    ]
    acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with acceptance_db_engine.begin() as conn:
        conn.execute(text("INSERT INTO compounds (compound_id, compound_name) VALUES ('C-01', 'Test Compound') ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO clinical_trials (trial_id, compound_id, trial_phase, therapeutic_area, status, target_enrollment) VALUES ('TRL-0019', 'C-01', 'Phase II', 'Oncology', 'Active', 100), ('TRL-0037', 'C-01', 'Phase II', 'Oncology', 'Active', 100) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO trial_sites (site_id, trial_id, site_name, country, enrollment_count, site_status) VALUES ('S-01', 'TRL-0019', 'Site', 'US', 59, 'Active'), ('S-02', 'TRL-0037', 'Site', 'US', 35, 'Active') ON CONFLICT DO NOTHING"))

    with Session(acceptance_db_engine) as session:
        state = run_acceptance_case(acceptance_gateway, session, "Which Phase II oncology trials are below 60% enrollment right now?")

    assert state.get("errors") == []
    assert state.get("validation_feedback") is None

def test_s1_invalid_query_id_regression(acceptance_db_engine, run_mode, acceptance_gateway):
    """Regression test proving invalid query_id results in a tool failure."""
    if run_mode == "live":
        pytest.skip("Regression test is offline-only")

    responses = [
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="sql_query_tool", arguments={"query_id": "invalid_hallucinated_id", "parameters": {}})]),
        LLMResponse(content=json.dumps({"summary": "I failed because of tool error", "limitations": []})),
        LLMResponse(content=json.dumps({"is_supported": True, "reason": "Yes"}))
    ]
    acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with Session(acceptance_db_engine) as session:
        state = run_acceptance_case(acceptance_gateway, session, "Which Phase II oncology trials are below 60% enrollment right now?")

    # Tool should have been called and returned an error
    tools = state.get("actual_tools", [])
    assert any(t["tool_name"] == "sql_query_tool" for t in tools)

    # Find the sql tool execution
    sql_exec = next(t for t in tools if t["tool_name"] == "sql_query_tool")
    assert "validation error for SqlQueryInput" in sql_exec["result"].get("error", "")

def test_s2_literature_rag(acceptance_db_engine, run_mode, acceptance_gateway):
    """S2: 'What has our internal research said about JAK2 inhibitors and cardiotoxicity?'"""
    if run_mode == "offline":
        responses = [
            LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="vector_search_tool", arguments={"query": "JAK2 inhibitors cardiotoxicity", "filters": {}})]),
            LLMResponse(content=json.dumps({"findings": "Internal research suggests XYZ.", "citations": ["doc1"], "search_quality": "High"})),
            LLMResponse(content=json.dumps({"is_supported": True, "reason": "Yes"}))
        ]
        acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with Session(acceptance_db_engine) as session:
        state = run_acceptance_case(acceptance_gateway, session, "What has our internal research said about JAK2 inhibitors and cardiotoxicity?")

    assert state.get("errors", []) == []
    assert "Literature Research" in state.get("specialist_results", {})

def test_s3_adverse_event(acceptance_db_engine, run_mode, acceptance_gateway):
    """S3: 'A site just reported a serious adverse event for Trial TRL-0034 — triage it.'"""
    if run_mode == "offline":
        responses = [
            LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="ae_severity_classifier_tool", arguments={"severity": "unknown", "seriousness": "serious", "adverse_event_term": "headache"})]),
            LLMResponse(content="", tool_calls=[ToolCall(id="t2", name="escalation_notifier_tool", arguments={"event_id": "AE-123", "reason": "serious"})]),
            LLMResponse(content=json.dumps({"explanation": "It was serious.", "final_severity": "Unknown", "final_seriousness": "Serious", "requires_review": True})),
            LLMResponse(content=json.dumps({"is_supported": True, "reason": "Yes"}))
        ]
        acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with Session(acceptance_db_engine) as session:
        state = run_acceptance_case(acceptance_gateway, session, "A site just reported a serious adverse event for Trial TRL-0034 — triage it.")

    assert state.get("errors", []) == []
    assert "Adverse Event Triage" in state.get("specialist_results", {})

def test_s4_compound_full_picture(acceptance_db_engine, run_mode, acceptance_gateway):
    """S4: 'Give me the full picture on compound DKU-1042: labs, trials, safety, and related literature.'"""
    if run_mode == "offline":
        responses = [
            # Trial
            LLMResponse(content=json.dumps({"summary": "Trial info", "limitations": []})),
            # Lit
            LLMResponse(content=json.dumps({"findings": "Lit info", "citations": [], "no_evidence_found": False})),
            # AE
            LLMResponse(content=json.dumps({"explanation": "None", "final_severity": "Unknown", "final_seriousness": "Unknown", "requires_review": False})),
            # Sim
            LLMResponse(content=json.dumps({"score": 0.9, "explanation": "Sim info", "coverage": 0.8})),
            # Report Writer
            LLMResponse(content=json.dumps({"report_text": "Synthesized full picture report.", "limitations_noted": [], "citations_resolved": []})),
            # Output Guardrail
            LLMResponse(content=json.dumps({"is_supported": True, "reason": "Yes"}))
        ]
        acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with Session(acceptance_db_engine) as session:
        state = run_acceptance_case(acceptance_gateway, session, "Give me the full picture on compound DKU-1042: labs, trials, safety, and related literature.")

    assert state.get("errors", []) == []
    assert "final_report" in state

def test_s5_compound_similarity(acceptance_db_engine, run_mode, acceptance_gateway):
    """S5: 'Find compounds similar to DKU-1042 and explain why they are considered similar.'"""
    if run_mode == "offline":
        responses = [
            LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="compound_similarity_tool", arguments={"compound_id": "DKU-1042"})]),
            LLMResponse(content=json.dumps({"score": 0.9, "explanation": "Explained.", "coverage": 0.9})),
            LLMResponse(content=json.dumps({"is_supported": True, "reason": "Yes"}))
        ]
        acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with Session(acceptance_db_engine) as session:
        state = run_acceptance_case(acceptance_gateway, session, "Find compounds similar to DKU-1042 and explain why they are considered similar.")

    assert state.get("errors", []) == []
    assert "Compound Similarity" in state.get("specialist_results", {})

def test_s6_report_writer(acceptance_db_engine, run_mode, acceptance_gateway):
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
            LLMResponse(content=json.dumps({"findings": "Lit info", "citations": [], "no_evidence_found": False})),
            LLMResponse(content=json.dumps({"report_text": "Synthesized full picture report.", "limitations_noted": [], "citations_resolved": []})),
            LLMResponse(content=json.dumps({"is_supported": True, "reason": "Yes"}))
        ]
        acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with Session(acceptance_db_engine) as session:
        state = run_acceptance_case(acceptance_gateway, session, "Summarize the findings from the trial analysis and literature research for DKU-1042.")

    assert state.get("errors", []) == []
    assert "final_report" in state

def test_s7_no_evidence(acceptance_db_engine, run_mode, acceptance_gateway):
    """S7: Unknown/nonexistent compound."""
    if run_mode == "offline":
        responses = [
            LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="sql_query_tool", arguments={"query_id": "compound_info", "parameters": {"compound_id": "UNKNOWN"}})]),
            LLMResponse(content=json.dumps({"summary": "No evidence found.", "limitations": []})),
            LLMResponse(content=json.dumps({"is_supported": True, "reason": "Yes"}))
        ]
        acceptance_gateway = LLMGateway(OfflineAdapter(responses))

    with Session(acceptance_db_engine) as session:
        state = run_acceptance_case(acceptance_gateway, session, "What clinical trials involve compound UNKNOWN-999?")

    assert state.get("errors", []) == []
    assert "Trial Data Analyst" in state.get("specialist_results", {})

def test_s8_medical_advice(acceptance_db_engine, run_mode, acceptance_gateway):
    """S8: 'What medication should a patient take for chest pain?'"""
    if run_mode == "offline":
        adp = OfflineAdapter([])
        acceptance_gateway = LLMGateway(adp)

    with Session(acceptance_db_engine) as session:
        state = run_acceptance_case(acceptance_gateway, session, "What medication should a patient take for chest pain?")

    assert state.get("errors") != []
    assert "Guardrail blocked request" in state.get("errors")[0]

    if run_mode == "offline":
        assert adp.call_count == 0

def test_s3_markdown_finalization_is_rejected(acceptance_db_engine, run_mode, acceptance_gateway):
    """Regression test proving that Markdown output at finalization is rejected."""
    if run_mode == "live":
        pytest.skip("Regression test is offline-only")

    responses = [
        # 1. SQL
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="ae_severity_classifier_tool", arguments={"severity": "unknown", "seriousness": "serious", "adverse_event_term": "headache"})]),
        # 2. Escalation
        LLMResponse(content="", tool_calls=[ToolCall(id="t2", name="escalation_notifier_tool", arguments={"event_id": "AE-123", "reason": "serious"})]),
        # 3. Finalization - Malformed Markdown instead of JSON!
        LLMResponse(content="## AE Triage Report\n\nI have finished triaging. It was serious. final_severity is Unknown.", tool_calls=[])
    ]

    adapter = OfflineAdapter(responses)
    acceptance_gateway = LLMGateway(adapter)

    with Session(acceptance_db_engine) as session:
        state = run_acceptance_case(acceptance_gateway, session, "A site just reported a serious adverse event for Trial TRL-0034 — triage it.")

    assert len(state.get("errors", [])) > 0
    assert any("not valid JSON" in err for err in state.get("errors", []))

def test_ae_specialist_no_data_terminates_cleanly(acceptance_db_engine, run_mode):
    """Regression test: AE specialist returns valid JSON when no data is found."""
    if run_mode == "live":
        pytest.skip("Offline only")

    responses = [
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="sql_query_tool", arguments={"query_id": "adverse_events_by_trial", "parameters": {"trial_id": "UNKNOWN"}})]),
        LLMResponse(content=json.dumps({"explanation": "No records found.", "final_severity": "Unknown", "final_seriousness": None, "requires_review": False}), tool_calls=[])
    ]

    from pharmasense.llm.gateway import LLMGateway
    from pharmasense.agents.adverse_event import create_ae_triage_agent

    gateway = LLMGateway(OfflineAdapter(responses))
    with Session(acceptance_db_engine) as session:
        agent = create_ae_triage_agent(session, gateway)
        result, tools = agent.run("Find AEs for UNKNOWN")

    assert result.final_severity == "Unknown"
    assert result.requires_review is False

def test_compound_similarity_no_data_terminates_cleanly(acceptance_db_engine, run_mode):
    """Regression test: Compound similarity returns valid JSON when no data is found."""
    if run_mode == "live":
        pytest.skip("Offline only")

    responses = [
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="compound_similarity_tool", arguments={"compound_id": "UNKNOWN"})]),
        LLMResponse(content=json.dumps({"score": 0.0, "explanation": "No data found.", "coverage": 0.0}), tool_calls=[])
    ]

    from pharmasense.llm.gateway import LLMGateway
    from pharmasense.agents.similarity import create_compound_similarity_agent

    gateway = LLMGateway(OfflineAdapter(responses))
    with Session(acceptance_db_engine) as session:
        agent = create_compound_similarity_agent(session, gateway)
        result, tools = agent.run("Compare UNKNOWN")

    assert result.score == 0.0
    assert result.coverage == 0.0

def test_s4_continues_when_specialist_has_no_evidence(acceptance_db_engine, run_mode):
    """Regression test: S4 completes successfully even if a specialist returns no data."""
    if run_mode == "live":
        pytest.skip("Offline only")

    responses = [
        # Trial
        LLMResponse(content=json.dumps({"summary": "Trial info", "limitations": []})),
        # Lit (NO EVIDENCE)
        LLMResponse(content=json.dumps({"findings": "No evidence.", "citations": [], "no_evidence_found": True})),
        # AE (NO EVIDENCE)
        LLMResponse(content=json.dumps({"explanation": "No records.", "final_severity": "Unknown", "final_seriousness": None, "requires_review": False})),
        # Sim (NO EVIDENCE)
        LLMResponse(content=json.dumps({"score": 0.0, "explanation": "Missing data.", "coverage": 0.0})),
        # Report Writer (Synthesis)
        LLMResponse(content=json.dumps({"report_text": "Synthesized full picture report despite no evidence.", "limitations_noted": ["No AE data", "No Lit data"], "citations_resolved": []})),
        # Output Guardrail
        LLMResponse(content=json.dumps({"is_supported": True, "reason": "Yes"}))
    ]

    from pharmasense.llm.gateway import LLMGateway
    gateway = LLMGateway(OfflineAdapter(responses))

    with Session(acceptance_db_engine) as session:
        state = run_acceptance_case(gateway, session, "Give me the full picture on compound DKU-1042.")

    assert state.get("errors", []) == []
    assert "final_report" in state
