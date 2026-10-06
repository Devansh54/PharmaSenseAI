import pytest
from pharmasense.agents.adverse_event import create_ae_triage_agent
from pharmasense.tools.escalation import escalation_notifier_tool
from pharmasense.llm.gateway import LLMGateway
from pharmasense.llm.contracts import ToolCall, LLMResponse, LLMProvider, LLMRequest
from sqlalchemy.orm import Session
import json

class DummyAdapter(LLMProvider):
    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp


def test_ae_triage_has_escalation_tool(pgvector_engine):
    with Session(pgvector_engine) as session:
        gateway = LLMGateway(DummyAdapter([]))
        agent = create_ae_triage_agent(session, gateway)
        assert "escalation_notifier_tool" in agent.tools

def test_serious_ae_triggers_escalation(pgvector_engine):
    # Serious AE -> escalation occurs
    responses = [
        # Call sql_query_tool
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="sql_query_tool", arguments={"query_id": "adverse_events_by_trial", "parameters": {"trial_id": "TRL-0034"}})]),
        # Call ae_severity_classifier_tool
        LLMResponse(content="", tool_calls=[ToolCall(id="t2", name="ae_severity_classifier_tool", arguments={"severity": "Severe", "seriousness": "Serious", "adverse_event_term": "Anemia"})]),
        # Call escalation_notifier_tool
        LLMResponse(content="", tool_calls=[ToolCall(id="t3", name="escalation_notifier_tool", arguments={"event_id": "AE-123", "reason": "Serious event"})]),
        # Final output
        LLMResponse(content=json.dumps({"explanation": "Escalated", "final_severity": "Severe", "final_seriousness": "Serious", "requires_review": True}))
    ]
    with Session(pgvector_engine) as session:
        gateway = LLMGateway(DummyAdapter(responses))
        agent = create_ae_triage_agent(session, gateway)
        result, tools_executed = agent.run("Triage TRL-0034")
        tool_names = [t["tool_name"] for t in tools_executed]
        assert "escalation_notifier_tool" in tool_names
        assert result.requires_review is True

def test_serious_unrelated_ae_triggers_escalation(pgvector_engine):
    # Serious + unrelated -> escalation occurs
    responses = [
        LLMResponse(content="", tool_calls=[ToolCall(id="t0", name="ae_severity_classifier_tool", arguments={"severity": "Severe", "seriousness": "Serious", "adverse_event_term": "Term"})]),
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="escalation_notifier_tool", arguments={"event_id": "AE-124", "reason": "Serious but unrelated"})]),
        LLMResponse(content=json.dumps({"explanation": "Escalated unrelated", "final_severity": "Severe", "final_seriousness": "Serious", "requires_review": True}))
    ]
    with Session(pgvector_engine) as session:
        gateway = LLMGateway(DummyAdapter(responses))
        agent = create_ae_triage_agent(session, gateway)
        result, tools_executed = agent.run("Triage unrelated serious")
        tool_names = [t["tool_name"] for t in tools_executed]
        assert "escalation_notifier_tool" in tool_names
        assert result.requires_review is True

def test_serious_resolved_ae_triggers_escalation(pgvector_engine):
    # Serious + resolved -> escalation occurs
    responses = [
        LLMResponse(content="", tool_calls=[ToolCall(id="t0", name="ae_severity_classifier_tool", arguments={"severity": "Severe", "seriousness": "Serious", "adverse_event_term": "Term"})]),
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="escalation_notifier_tool", arguments={"event_id": "AE-125", "reason": "Serious but resolved"})]),
        LLMResponse(content=json.dumps({"explanation": "Escalated resolved", "final_severity": "Severe", "final_seriousness": "Serious", "requires_review": True}))
    ]
    with Session(pgvector_engine) as session:
        gateway = LLMGateway(DummyAdapter(responses))
        agent = create_ae_triage_agent(session, gateway)
        result, tools_executed = agent.run("Triage resolved serious")
        tool_names = [t["tool_name"] for t in tools_executed]
        assert "escalation_notifier_tool" in tool_names
        assert result.requires_review is True

def test_non_serious_no_escalation(pgvector_engine):
    # Non-serious -> no serious-event escalation
    responses = [
        LLMResponse(content=json.dumps({"explanation": "Non-serious", "final_severity": "Moderate", "final_seriousness": "Non-serious", "requires_review": False}))
    ]
    with Session(pgvector_engine) as session:
        gateway = LLMGateway(DummyAdapter(responses))
        agent = create_ae_triage_agent(session, gateway)
        result, tools_executed = agent.run("Triage non-serious")
        tool_names = [t["tool_name"] for t in tools_executed]
        assert "escalation_notifier_tool" not in tool_names
        assert result.requires_review is False

def test_unknown_seriousness_no_escalation(pgvector_engine):
    # Unknown seriousness -> no false escalation
    responses = [
        LLMResponse(content=json.dumps({"explanation": "Unknown", "final_severity": "Moderate", "final_seriousness": None, "requires_review": False}))
    ]
    with Session(pgvector_engine) as session:
        gateway = LLMGateway(DummyAdapter(responses))
        agent = create_ae_triage_agent(session, gateway)
        result, tools_executed = agent.run("Triage unknown")
        tool_names = [t["tool_name"] for t in tools_executed]
        assert "escalation_notifier_tool" not in tool_names
        assert result.requires_review is False

def test_llm_cannot_bypass_tools_for_serious_ae(pgvector_engine):
    responses = [
        # LLM skips both tools and just finalizes directly claiming it is Serious
        LLMResponse(content=json.dumps({"explanation": "I am skipping tools", "final_severity": "Severe", "final_seriousness": "Serious", "requires_review": True})),
        # Agent should reject it and ask LLM to try again. LLM then calls tools:
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="ae_severity_classifier_tool", arguments={"severity": "Severe", "seriousness": "Serious", "adverse_event_term": "Term"})]),
        LLMResponse(content="", tool_calls=[ToolCall(id="t2", name="escalation_notifier_tool", arguments={"event_id": "AE-123", "reason": "Serious"})]),
        LLMResponse(content=json.dumps({"explanation": "Fixed", "final_severity": "Severe", "final_seriousness": "Serious", "requires_review": True}))
    ]
    with Session(pgvector_engine) as session:
        dummy = DummyAdapter(responses)
        gateway = LLMGateway(dummy)
        agent = create_ae_triage_agent(session, gateway)
        result, tools = agent.run("Prompt")
        # Ensure it actually did the retries
        assert dummy.call_count == 4
        tool_names = [t["tool_name"] for t in tools]
        assert "ae_severity_classifier_tool" in tool_names
        assert "escalation_notifier_tool" in tool_names

def test_llm_cannot_bypass_tools_if_sql_returns_serious(pgvector_engine, monkeypatch):
    import pharmasense.agents.adverse_event
    from pharmasense.tools.sql_query import SqlQueryInput

    # We patch sql_query_tool so it returns a serious event
    def fake_sql(input_data: SqlQueryInput, session=None):
        return {"results": [{"event_id": "AE-999", "seriousness": "Serious"}], "columns": ["event_id", "seriousness"]}

    monkeypatch.setattr(pharmasense.agents.adverse_event, "sql_query_tool", fake_sql)

    responses = [
        # 1. Calls SQL
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="sql_query_tool", arguments={"query_id": "adverse_events_by_trial", "parameters": {"trial_id": "TRL"}})]),
        # 2. LLM ignores the serious AE and just returns Non-serious to try and bypass
        LLMResponse(content=json.dumps({"explanation": "I am hiding the serious AE", "final_severity": "Mild", "final_seriousness": "Non-serious", "requires_review": False})),
        # 3. Agent rejects because SQL returned Serious! So LLM now calls classifier
        LLMResponse(content="", tool_calls=[ToolCall(id="t2", name="ae_severity_classifier_tool", arguments={"severity": "Severe", "seriousness": "Serious", "adverse_event_term": "Term"})]),
        # 4. LLM calls escalation
        LLMResponse(content="", tool_calls=[ToolCall(id="t3", name="escalation_notifier_tool", arguments={"event_id": "AE", "reason": "Serious"})]),
        # 5. Final
        LLMResponse(content=json.dumps({"explanation": "Fixed", "final_severity": "Severe", "final_seriousness": "Serious", "requires_review": True}))
    ]

    with Session(pgvector_engine) as session:
        dummy = DummyAdapter(responses)
        gateway = LLMGateway(dummy)
        agent = create_ae_triage_agent(session, gateway)
        result, tools = agent.run("Prompt")
        assert dummy.call_count == 5
        tool_names = [t["tool_name"] for t in tools]
        assert "ae_severity_classifier_tool" in tool_names
        assert "escalation_notifier_tool" in tool_names
