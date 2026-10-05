import json
from pharmasense.llm.contracts import LLMProvider, LLMRequest, LLMResponse, ToolCall
from pharmasense.llm.gateway import LLMGateway
from pharmasense.orchestration.graph import build_orchestration_graph

class TokenTraceAdapter(LLMProvider):
    def __init__(self):
        self.call_idx = 0
        self.call_sizes = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        from pharmasense.llm.groq_adapter import _to_groq_messages, _to_groq_tools, _to_groq_response_format
        
        messages = _to_groq_messages(request.messages)
        tools = _to_groq_tools(request)
        response_format = _to_groq_response_format(request)
        
        sizes = {
            "system": sum(len(m.get("content", "")) for m in messages if m.get("role") == "system"),
            "user": sum(len(m.get("content", "")) for m in messages if m.get("role") == "user"),
            "tools": len(json.dumps(tools)) if tools else 0,
            "response_schema": len(json.dumps(response_format)) if response_format else 0,
            "tool_result": sum(len(m.get("content", "")) for m in messages if m.get("role") == "tool")
        }
        self.call_sizes.append(sizes)
            
        self.call_idx += 1
        
        # We only want to measure the Trial Data Analyst calls, but we need to satisfy the graph
        if request.response_schema and request.response_schema.get("title") == "Plan":
            return LLMResponse(content="", parsed={"workflow_type": "single", "selected_specialists": ["Trial Data Analyst"], "task_descriptions": {"Trial Data Analyst": "Use the trial_enrollment_stats query_id"}})
            
        if "sql_query_tool" in json.dumps(tools):
            if not any(m.get("role") == "tool" for m in messages):
                return LLMResponse(content='', tool_calls=[ToolCall(id='t1', name='sql_query_tool', arguments={'query_id': 'trial_enrollment_stats', 'parameters': {'trial_phase': 'Phase II', 'therapeutic_area': 'Oncology'}})])
            else:
                return LLMResponse(content='', parsed={"summary": "Test", "limitations": []})
                
        return LLMResponse(content=json.dumps({'summary': 'Test', 'limitations': []}), parsed={"summary": "Test", "limitations": []})

def test_s1_payload_size(pgvector_engine):
    adapter = TokenTraceAdapter()
    gateway = LLMGateway(adapter)
    
    with pgvector_engine.connect() as conn:
        graph = build_orchestration_graph(conn, gateway)
        graph.invoke({'request_id': 'test', 'user_prompt': 'Which Phase II oncology trials are below 60% enrollment right now?'})
        
    trial_calls = [c for c in adapter.call_sizes if c.get("tools") == 767 or c.get("response_schema") == 448]
    assert len(trial_calls) == 2, f"Expected 2 Trial Analyst calls, got {len(trial_calls)}"
    
    call1 = trial_calls[0]
    call2 = trial_calls[1]
    
    # 1 token roughly 4 characters
    call1_tokens = sum(call1.values()) / 4
    call2_tokens = sum(call2.values()) / 4
    
    print(f"CALL 1 sizes: {call1}")
    print(f"CALL 2 sizes: {call2}")
    print(f"CALL 1 ~{call1_tokens:.0f} tokens")
    print(f"CALL 2 ~{call2_tokens:.0f} tokens")
    
    assert call1_tokens <= 850, f"CALL 1 token size {call1_tokens} > 850 target"
    assert call2_tokens <= 600, f"CALL 2 token size {call2_tokens} > 600 target"
