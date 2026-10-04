import pytest
from unittest.mock import MagicMock
from pydantic import BaseModel

from pharmasense.llm.contracts import LLMProvider, LLMRequest, LLMResponse, ToolCall
from pharmasense.agents.base import BaseAgent

class DummyInput(BaseModel):
    query: str

class DummyOutput(BaseModel):
    result: str

def dummy_tool(input_data: DummyInput, session=None) -> dict:
    return {"status": "ok", "echo": input_data.query}

class MockLLM(LLMProvider):
    def __init__(self, responses: list[LLMResponse]):
        self.responses = responses
        self.call_count = 0
        self.requests = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self.call_count >= len(self.responses):
            raise RuntimeError("Mock out of responses")
        res = self.responses[self.call_count]
        self.call_count += 1
        return res

def test_base_agent_tool_loop():
    resp1 = LLMResponse(
        content="Thinking...",
        tool_calls=[ToolCall(id="call_1", name="dummy_tool", arguments={"query": "test"})]
    )
    resp2 = LLMResponse(
        content="Done",
        parsed={"result": "success"}
    )

    mock_llm = MockLLM([resp1, resp2])
    agent = BaseAgent(
        session=MagicMock(),
        llm=mock_llm,
        system_instruction="You are a dummy agent",
        tools={"dummy_tool": dummy_tool},
        output_model=DummyOutput
    )

    out, _ = agent.run("Do something")

    assert isinstance(out, DummyOutput)
    assert out.result == "success"
    assert mock_llm.call_count == 2

    req2 = mock_llm.requests[1]
    tool_msgs = [m for m in req2.messages if m.role == "tool"]
    assert len(tool_msgs) == 1
    assert "echo" in tool_msgs[0].content
    assert "test" in tool_msgs[0].content


def test_base_agent_exceeds_budget():
    resp1 = LLMResponse(
        content="Thinking...",
        tool_calls=[ToolCall(id="call_1", name="dummy_tool", arguments={"query": "test"})]
    )

    mock_llm = MockLLM([resp1] * 10)
    agent = BaseAgent(
        session=MagicMock(),
        llm=mock_llm,
        system_instruction="You are a dummy agent",
        tools={"dummy_tool": dummy_tool},
        output_model=DummyOutput,
        max_iterations=3
    )

    with pytest.raises(RuntimeError, match="exceeded max iterations"):
        agent.run("Do something")

def test_base_agent_unauthorized_tool():
    resp1 = LLMResponse(
        content="Thinking...",
        tool_calls=[ToolCall(id="call_1", name="forbidden_tool", arguments={"query": "test"})]
    )
    mock_llm = MockLLM([resp1])
    agent = BaseAgent(
        session=MagicMock(),
        llm=mock_llm,
        system_instruction="You are a dummy agent",
        tools={"dummy_tool": dummy_tool},
        output_model=DummyOutput
    )

    with pytest.raises(RuntimeError, match="unauthorized tool: forbidden_tool"):
        agent.run("Do something")

from pharmasense.llm.contracts import LLMGatewayError, LLMProviderError

def test_base_agent_retries_on_schema_error():
    resp_success = LLMResponse(
        content='{"result": "success"}',
        parsed={"result": "success"},
        tool_calls=[]
    )
    mock_llm = MagicMock()
    mock_llm.complete.side_effect = [
        LLMGatewayError("Structured output parsing failed: Missing field 'result'"),
        resp_success
    ]

    agent = BaseAgent(
        session=MagicMock(),
        llm=mock_llm,
        system_instruction="sys",
        tools={},
        output_model=DummyOutput,
        max_iterations=3
    )

    out, tools = agent.run("prompt")

    assert out.result == "success"
    assert mock_llm.complete.call_count == 2
    req2 = mock_llm.complete.call_args_list[1][0][0]
    assert "Your previous response was invalid" in req2.messages[-1].content
    assert "Missing field 'result'" in req2.messages[-1].content

def test_base_agent_propagates_provider_error():
    mock_llm = MagicMock()
    mock_llm.complete.side_effect = LLMProviderError("Rate limit exceeded")

    agent = BaseAgent(
        session=MagicMock(),
        llm=mock_llm,
        system_instruction="sys",
        tools={},
        output_model=DummyOutput,
        max_iterations=3
    )

    with pytest.raises(LLMProviderError):
        agent.run("prompt")
