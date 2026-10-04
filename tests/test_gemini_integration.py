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
