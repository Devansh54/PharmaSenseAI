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
