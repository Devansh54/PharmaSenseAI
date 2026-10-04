import pytest
from pharmasense.llm.contracts import ToolSpec, LLMRequest, Message, ToolCall, LLMResponse
from pharmasense.llm.gemini_adapter import _to_gemini_tools, _to_gemini_messages
from google.genai import types

def test_gemini_schema_transformation():
    """Verify GeminiAdapter strips additionalProperties to create an API-compatible schema."""
    t = ToolSpec(
        name="test_tool",
        description="A test tool",
        parameters={
            "type": "object",
            "properties": {
                "arg1": {"type": "string"},
                "nested": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"arg2": {"type": "integer"}}
                }
            },
            "additionalProperties": False,
            "title": "TestSchema"
        }
    )
    req = LLMRequest(messages=[], model="test", tools=[t])
    tools = _to_gemini_tools(req)

    assert tools is not None
    assert len(tools) == 1
    func_decl = tools[0].function_declarations[0]
    assert func_decl.name == "test_tool"

    params = func_decl.parameters
    assert "additionalProperties" not in params
    assert "title" not in params
    assert "additionalProperties" not in params["properties"]["nested"]
    assert params["properties"]["nested"]["properties"]["arg2"]["type"] == "integer"

def test_gemini_continuation_metadata():
    """Verify GeminiAdapter preserves continuation metadata (parts)."""
    # Create fake parts to represent a raw Gemini model turn with a tool call and thought signature
    part1 = types.Part.from_text(text="I am thinking.")
    part2 = types.Part.from_function_call(name="test_tool", args={"arg1": "val"})
    raw_parts = [part1, part2]

    # Assume LLMResponse has these parts stored in provider_metadata
    messages = [
        Message(
            role="assistant",
            content="I am thinking.",
            tool_calls=[ToolCall(id="1", name="test_tool", arguments={"arg1": "val"})],
            provider_metadata=raw_parts
        )
    ]

    # Converting back to Gemini messages should reuse the raw parts
    gemini_messages = _to_gemini_messages(messages)
    assert len(gemini_messages) == 1
    assert gemini_messages[0].role == "model"
    # It should have exactly the original parts
    assert gemini_messages[0].parts == raw_parts

def test_gemini_raw_text_fallback():
    """Verify GeminiAdapter falls back to raw.text when parts yield no text content.

    This covers the case where Gemini returns structured JSON via response_mime_type
    and some SDK versions surface the result via response.text rather than parts[].text.
    """
    from unittest.mock import MagicMock, patch
    from pharmasense.llm.gemini_adapter import GeminiAdapter
    from pharmasense.llm.contracts import LLMRequest, Message

    # Build a mock SDK response where text_parts is empty but raw.text is populated
    mock_part = MagicMock()
    mock_part.text = ""          # empty — simulates JSON schema response
    mock_part.function_call = None

    mock_candidate = MagicMock()
    mock_candidate.content = MagicMock()
    mock_candidate.content.parts = [mock_part]
    mock_candidate.finish_reason = MagicMock()
    mock_candidate.finish_reason.name = "STOP"

    mock_raw = MagicMock()
    mock_raw.candidates = [mock_candidate]
    mock_raw.text = '{"workflow_type": "single"}'
    mock_raw.usage_metadata = None

    with patch("pharmasense.llm.gemini_adapter.GeminiAdapter.__init__", return_value=None):
        adapter = GeminiAdapter.__new__(GeminiAdapter)
        adapter._config = MagicMock()
        adapter._config.model = "gemini-test"
        adapter._client = MagicMock()
        adapter._client.models.generate_content.return_value = mock_raw

    req = LLMRequest(
        messages=[Message(role="user", content="plan this")],
        model="gemini-test",
        response_schema={"type": "object", "properties": {"workflow_type": {"type": "string"}}}
    )
    resp = adapter.complete(req)
    assert resp.content == '{"workflow_type": "single"}'

def test_gemini_tool_calls_coalesced():
    """Verify multiple tool responses are coalesced into a single user turn."""
    messages = [
        Message(role="tool", name="tool_1", content='{"res": 1}', tool_call_id="call_1"),
        Message(role="tool", name="tool_2", content='{"res": 2}', tool_call_id="call_2")
    ]
    gemini_messages = _to_gemini_messages(messages)
    assert len(gemini_messages) == 1
    assert gemini_messages[0].role == "user"
    assert len(gemini_messages[0].parts) == 2
    assert gemini_messages[0].parts[0].function_response.name == "tool_1"
    assert gemini_messages[0].parts[1].function_response.name == "tool_2"

def test_gemini_function_call_ignores_raw_text_fallback():
    """Verify GeminiAdapter doesn't hit raw.text fallback on function_call parts."""
    from unittest.mock import MagicMock, patch
    from pharmasense.llm.gemini_adapter import GeminiAdapter
    from pharmasense.llm.contracts import LLMRequest, Message

    mock_part = MagicMock()
    mock_part.text = None
    mock_part.function_call = MagicMock()
    mock_part.function_call.name = "test_tool"
    mock_part.function_call.args = {"arg": "val"}

    mock_candidate = MagicMock()
    mock_candidate.content = MagicMock()
    mock_candidate.content.parts = [mock_part]
    mock_candidate.finish_reason = None

    mock_raw = MagicMock()
    mock_raw.candidates = [mock_candidate]
    type(mock_raw).text = property(lambda self: "SHOULD_NOT_BE_ACCESSED")
    mock_raw.usage_metadata = None

    with patch("pharmasense.llm.gemini_adapter.GeminiAdapter.__init__", return_value=None):
        adapter = GeminiAdapter.__new__(GeminiAdapter)
        adapter._config = MagicMock()
        adapter._config.model = "gemini-test"
        adapter._client = MagicMock()
        adapter._client.models.generate_content.return_value = mock_raw

    req = LLMRequest(messages=[Message(role="user", content="call it")], model="gemini-test")
    resp = adapter.complete(req)

    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "test_tool"
    assert resp.content is None

def test_gemini_e2e_multiturn_tool_loop():
    """Verify end-to-end multi-turn tool calling through GeminiAdapter and BaseAgent."""
    from unittest.mock import MagicMock, patch
    from pydantic import BaseModel
    from pharmasense.llm.gemini_adapter import GeminiAdapter
    from pharmasense.agents.base import BaseAgent

    class DummyOutput(BaseModel):
        status: str

    def dummy_tool(input_data: DummyOutput) -> dict:
        return {"result": "success"}

    # Build Gemini Turn 1 (function call)
    mock_part1 = MagicMock()
    mock_part1.text = None
    mock_part1.function_call = MagicMock()
    mock_part1.function_call.name = "dummy_tool"
    mock_part1.function_call.args = {"status": "ok"}

    mock_candidate1 = MagicMock()
    mock_candidate1.content = MagicMock()
    mock_candidate1.content.parts = [mock_part1]
    mock_candidate1.finish_reason = None

    mock_raw1 = MagicMock()
    mock_raw1.candidates = [mock_candidate1]
    mock_raw1.usage_metadata = None

    # Build Gemini Turn 2 (parsed response)
    mock_part2 = MagicMock()
    mock_part2.text = '{"status": "done"}'
    mock_part2.function_call = None

    mock_candidate2 = MagicMock()
    mock_candidate2.content = MagicMock()
    mock_candidate2.content.parts = [mock_part2]
    mock_candidate2.finish_reason = None

    mock_raw2 = MagicMock()
    mock_raw2.candidates = [mock_candidate2]
    mock_raw2.usage_metadata = None

    # Track calls to generate_content to assert requests
    generate_calls = []

    def side_effect(*args, **kwargs):
        generate_calls.append(kwargs)
        if len(generate_calls) == 1:
            return mock_raw1
        return mock_raw2

    with patch("pharmasense.llm.gemini_adapter.GeminiAdapter.__init__", return_value=None):
        adapter = GeminiAdapter.__new__(GeminiAdapter)
        adapter._config = MagicMock()
        adapter._config.model = "gemini-test"
        adapter._client = MagicMock()
        adapter._client.models.generate_content.side_effect = side_effect

    from pharmasense.llm.gateway import LLMGateway
    gateway = LLMGateway(provider=adapter)

    agent = BaseAgent(
        session=MagicMock(),
        llm=gateway,
        system_instruction="sys",
        tools={"dummy_tool": dummy_tool},
        output_model=DummyOutput,
        model_name="gemini-test"
    )

    output, tools_used = agent.run("test prompt")

    # Assert BaseAgent completes successfully
    assert output.status == "done"
    assert len(tools_used) == 1
    assert tools_used[0]["tool_name"] == "dummy_tool"

    # Assert Turn 2 request reconstructed conversation correctly
    assert len(generate_calls) == 2
    turn2_request_contents = generate_calls[1]["contents"]

    # Expected turns:
    # 0: user ("test prompt")
    # 1: model (contains function_call)
    # 2: user (contains function_response)
    assert len(turn2_request_contents) == 3
    assert turn2_request_contents[0].role == "user"
    assert turn2_request_contents[1].role == "model"
    assert turn2_request_contents[2].role == "user"

    # The model turn must have the exact original part containing function_call
    assert turn2_request_contents[1].parts[0].function_call.name == "dummy_tool"
    assert turn2_request_contents[1].parts[0].function_call.args == {"status": "ok"}

    # The second user turn must have the function_response part
    assert len(turn2_request_contents[2].parts) == 1
    assert turn2_request_contents[2].parts[0].function_response.name == "dummy_tool"
