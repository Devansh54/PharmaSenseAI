import pytest
from unittest.mock import MagicMock, patch

from pharmasense.llm.contracts import LLMRequest, Message, LLMResponse, LLMProviderError, ToolSpec
from pharmasense.orchestration.planner import PlannerNode
from pharmasense.llm.gemini_adapter import _sanitize_schema_for_gemini, GeminiAdapter
from pharmasense.llm.gateway import LLMGateway
from pharmasense.orchestration.state import Plan
from pharmasense.config import GeminiAdapterConfig

def test_planner_sends_system_and_user_message():
    """1. Planner sends both system instructions and valid user/content payload."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = LLMResponse(
        content="{}",
        parsed={"selected_specialists": ["Trial Data Analyst"], "workflow_type": "single", "task_descriptions": {}}
    )

    planner = PlannerNode(mock_llm)
    planner({"user_prompt": "Test Prompt"})

    # Verify request
    req: LLMRequest = mock_llm.complete.call_args[0][0]
    assert len(req.messages) == 2
    assert req.messages[0].role == "system"
    assert "Router/Planner" in req.messages[0].content
    assert req.messages[1].role == "user"
    assert "Test Prompt" in req.messages[1].content

def test_planner_does_not_hardcode_model():
    """2. Planner does not hardcode any provider/model."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = LLMResponse(
        content="{}",
        parsed={"selected_specialists": ["Trial Data Analyst"], "workflow_type": "single", "task_descriptions": {}}
    )

    planner = PlannerNode(mock_llm)
    planner({"user_prompt": "Test Prompt"})

    req: LLMRequest = mock_llm.complete.call_args[0][0]
    assert req.model == "" or req.model is None

@patch("pharmasense.llm.gemini_adapter.genai")
def test_gateway_config_controls_planner(mock_genai):
    """3. Gateway configuration controls the planner's provider/model."""
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client

    adapter = GeminiAdapter(config=GeminiAdapterConfig(model="gemini-3.5-flash-lite", api_key="fake"))

    req = LLMRequest(
        messages=[Message(role="user", content="Test")],
        model="" # Planner sends empty string
    )

    # Mock return so it doesn't crash
    mock_raw = MagicMock()
    mock_raw.candidates = []
    mock_client.models.generate_content.return_value = mock_raw

    adapter.complete(req)

    # Ensure client called with model from config
    mock_client.models.generate_content.assert_called_once()
    kwargs = mock_client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-3.5-flash-lite"

def test_gemini_schema_is_transformed():
    """4. Gemini structured-output schema is transformed into an API-compatible schema."""
    schema = {
        "type": "object",
        "title": "TestObject",
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
                "title": "Name",
                "default": "Unknown"
            }
        }
    }
    sanitized = _sanitize_schema_for_gemini(schema)
    assert "additionalProperties" not in sanitized
    assert "title" not in sanitized
    assert "title" not in sanitized["properties"]["name"]
    assert "default" not in sanitized["properties"]["name"]

def test_gemini_structured_output_still_validated():
    """5. Returned Gemini structured output is still validated against the application Plan model."""
    mock_llm = MagicMock()
    # Provide parsed dict missing required fields
    mock_llm.complete.return_value = LLMResponse(
        content="{}",
        parsed={"workflow_type": "single"} # missing selected_specialists
    )

    planner = PlannerNode(mock_llm)
    res = planner({"user_prompt": "Test Prompt"})

    assert "errors" in res
    assert "Validation Error:" in res["errors"][0]

@patch("pharmasense.llm.gateway.parse_and_validate")
def test_openai_behavior_unchanged(mock_parse):
    """6. Existing OpenAI behavior is not broken (Gateway still calls standard validation)."""
    # Gateway parse_and_validate handles schema validation for all providers
    gateway = LLMGateway(MagicMock())
    req = LLMRequest(
        messages=[Message(role="user", content="Test")],
        model="",
        response_schema={"type": "object"}
    )

    # Simulate a response from ANY provider
    mock_response = LLMResponse(content='{"valid": true}', model="any")
    gateway._provider.complete.return_value = mock_response
    mock_parse.return_value = {"valid": True}

    res = gateway.complete(req)
    assert res.parsed == {"valid": True}
    mock_parse.assert_called_once_with('{"valid": true}', {"type": "object"})

def test_gemini_tool_calling_compatible():
    """7. Gemini tool-calling behavior remains compatible with the existing LLMResponse contract."""
    from pharmasense.llm.gemini_adapter import _parse_tool_calls
    mock_parts = []

    mock_part = MagicMock()
    mock_part.function_call = MagicMock()
    mock_part.function_call.name = "get_weather"
    mock_part.function_call.args = {"location": "Tokyo"}
    mock_parts.append(mock_part)

    calls = _parse_tool_calls(mock_parts)
    assert len(calls) == 1
    assert calls[0].name == "get_weather"
    assert calls[0].arguments == {"location": "Tokyo"}

def test_planner_exceptions_not_silently_converted():
    """8. Planner exceptions are not silently converted into an apparent successful fallback benchmark result."""
    mock_llm = MagicMock()
    mock_llm.complete.side_effect = LLMProviderError("400 Bad Request")

    planner = PlannerNode(mock_llm)

    # Instead of silently returning {"errors": ...}, the exception should bubble up
    with pytest.raises(LLMProviderError):
        planner({"user_prompt": "Test Prompt"})
