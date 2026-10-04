import pytest
import datetime
from sqlalchemy.orm import Session
from pharmasense.observability.telemetry import TelemetryManager, TelemetryTracer
from pharmasense.db.models import RuntimeTrace, RuntimeEvent
from pharmasense.llm.contracts import LLMProvider, LLMRequest, LLMResponse, Usage, CostBreakdown
from pharmasense.llm.gateway import LLMGateway
from pharmasense.orchestration.graph import build_orchestration_graph

class MockOpenAIAdapter(LLMProvider):
    def complete(self, request: LLMRequest) -> LLMResponse:
        content = "test"
        sys_prompt = request.messages[0].content.lower() if request.messages else ""
        user_prompt = request.messages[-1].content.lower() if request.messages else ""
        
        tool_calls = []
        if "router/planner" in sys_prompt or "planner" in sys_prompt:
            if "escalate" in user_prompt:
                content = '{"workflow_type": "single", "selected_specialists": ["Trial Data Analyst"], "task_descriptions": {"Trial Data Analyst": "escalate"}, "resolved_entities": {}}'
            else:
                content = '{"workflow_type": "single", "selected_specialists": ["Trial Data Analyst"], "task_descriptions": {"Trial Data Analyst": "t"}, "resolved_entities": {}}'
        elif "agent" in sys_prompt or "specialist" in sys_prompt or "trial" in sys_prompt:
            if "escalate" in user_prompt:
                print(f"Mock Adapter returning escalation for user prompt: {user_prompt}")
                from pharmasense.llm.contracts import ToolCall
                tool_calls = [ToolCall(id="call_1", name="escalation_notifier_tool", arguments={})]
                content = ""
            else:
                print(f"Mock Adapter NOT returning escalation for user prompt: {user_prompt}")
                
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=Usage(total_tokens=10, prompt_tokens=5, completion_tokens=5),
            cost=CostBreakdown(total_cost=0.001, prompt_cost=0.0005, completion_cost=0.0005)
        )

def test_telemetry_trace_continuity(pgvector_engine):
    with Session(pgvector_engine) as test_session:
        manager = TelemetryManager(test_session)
        tracer = TelemetryTracer(manager)
        
        mock_llm = MockOpenAIAdapter()
        gateway = LLMGateway(mock_llm, tracer=tracer)
        
        # We pass gateway as the llm provider!
        graph = build_orchestration_graph(test_session, gateway, telemetry_manager=manager)
        
        trace_id = "test-trace-001"
        manager.start_trace(trace_id=trace_id, dataset_version="test-1", workflow_version="test-1")
        
        result = graph.invoke({"request_id": trace_id, "user_prompt": "Find trial data for CMP-0001"})
        
        manager.end_trace(trace_id, status="SUCCESS", end_time=datetime.datetime.utcnow())
        
        # Verify Trace
        trace = test_session.query(RuntimeTrace).filter_by(trace_id=trace_id).first()
        assert trace is not None
        assert trace.status == "SUCCESS"
        assert trace.dataset_version == "test-1"
        assert trace.latency_sec > 0
        
        # Verify Events
        events = test_session.query(RuntimeEvent).filter_by(trace_id=trace_id).all()
        assert len(events) > 0
        
        event_types = {e.event_type for e in events}
        assert "PLANNER" in event_types
        assert "SPECIALIST" in event_types
        assert "LLM" in event_types
        
        # Verify Tokens & Cost Aggregation
        llm_events = [e for e in events if e.event_type == "LLM"]
        assert len(llm_events) > 0
        total_tokens = sum(e.prompt_tokens + e.completion_tokens for e in llm_events)
        assert trace.total_tokens == total_tokens
        
        # Ensure PII is absent
        for e in events:
            if e.event_metadata:
                assert "user_prompt" not in e.event_metadata or "[REDACTED]" in e.event_metadata
                assert "report_content" not in e.event_metadata or "[REDACTED]" in e.event_metadata
                
        # Test escalation
        trace_id_esc = "test-esc-001"
        manager.start_trace(trace_id=trace_id_esc)
        graph.invoke({"request_id": trace_id_esc, "user_prompt": "escalate to human"})
        manager.end_trace(trace_id_esc, status="SUCCESS", end_time=datetime.datetime.utcnow())
        
        trace_esc = test_session.query(RuntimeTrace).filter_by(trace_id=trace_id_esc).first()
        if not trace_esc.escalated:
            events = test_session.query(RuntimeEvent).filter_by(trace_id=trace_id_esc).all()
            for e in events:
                print(f"[{e.event_type}] Node: {e.node_name}, Status: {e.status}, Metadata: {e.event_metadata}")
        assert trace_esc.escalated is True
