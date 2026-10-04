import json
import logging
from unittest.mock import MagicMock, patch
from pharmasense.llm.gateway import LLMGateway
from pharmasense.llm.contracts import LLMProvider, LLMRequest, LLMResponse, ToolCall, Message
from pharmasense.orchestration.graph import build_orchestration_graph


logging.basicConfig(level=logging.ERROR)

class DummyAdapter(LLMProvider):
    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self._config = MagicMock()
        self._config.model = "dummy-model"
        self._config.pricing = {}
        
    def complete(self, request: LLMRequest) -> LLMResponse:
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp

def test_pipeline():
    session = MagicMock()
    
    # ----------------------------------------
    # B. Single SQL specialist
    # ----------------------------------------
    # Planner -> Trial Analyst -> SQL tool -> result -> final answer
    print("Testing B: Single SQL Specialist...")
    
    responses = [
        # 0. Input Guardrail
        LLMResponse(content=json.dumps({
            "is_safe": True,
            "reason": "safe"
        })),
        # 1. Planner routing to Trial Data Analyst
        LLMResponse(content=json.dumps({
            "workflow_type": "single",
            "selected_specialists": ["Trial Data Analyst"],
            "task_descriptions": {"Trial Data Analyst": "find trial data"},
            "resolved_entities": {}
        })),
        # 2. Trial Data Analyst calling SQL tool
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="call_1", name="sql_query_tool", arguments={"query": "SELECT * FROM trials"})]
        ),
        # 3. Trial Data Analyst final answer
        LLMResponse(content=json.dumps({
            "summary": "Trial found.",
            "limitations": []
        })),
        # 4. Report Writer
        LLMResponse(content=json.dumps({
            "report_text": "The trial was found.",
            "limitations_noted": [],
            "citations_resolved": []
        })),
        # 5. Output Guardrail (evidence validation)
        LLMResponse(content=json.dumps({
            "is_supported": True,
            "reason": "supported"
        }))
    ]
    
    adapter = DummyAdapter(responses)
    gateway = LLMGateway(adapter)
    
    graph = build_orchestration_graph(session, gateway)
    final_state = graph.invoke({"request_id": "req_1", "user_prompt": "What is trial X?"})
    
    assert final_state.get("errors", []) == []
    assert final_state.get("final_report", {}).get("report_text") == "The trial was found."
