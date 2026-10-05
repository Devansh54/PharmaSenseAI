import pytest
from unittest.mock import MagicMock
from pharmasense.llm.groq_adapter import GroqAdapter
from pharmasense.llm.contracts import LLMRequest, Message, ToolSpec, LLMProviderError
from pharmasense.config import GroqAdapterConfig

def test_tool_call_request_has_no_response_format():
    adapter = GroqAdapter(config=GroqAdapterConfig(api_key="fake"), client=MagicMock())
    req = LLMRequest(
        model="qwen",
        messages=[Message(role="user", content="Hello")],
        tools=[ToolSpec(name="test_tool", description="test")],
        response_schema={"type": "object", "properties": {"name": {"type": "string"}}}
    )
    
    mock_raw = MagicMock()
    mock_raw.choices[0].message.content = "OK"
    adapter._client.chat.completions.create.return_value = mock_raw
    
    adapter.complete(req)
    
    kwargs = adapter._client.chat.completions.create.call_args.kwargs
    assert "tools" in kwargs
    assert "response_format" not in kwargs

def test_final_structured_request_has_json_schema_and_no_tools():
    adapter = GroqAdapter(config=GroqAdapterConfig(api_key="fake"), client=MagicMock())
    req = LLMRequest(
        model="qwen",
        messages=[Message(role="user", content="Hello")],
        tools=None,
        response_schema={"type": "object", "properties": {"name": {"type": "string"}}}
    )
    
    mock_raw = MagicMock()
    mock_raw.choices[0].message.content = "{}"
    adapter._client.chat.completions.create.return_value = mock_raw
    
    adapter.complete(req)
    
    kwargs = adapter._client.chat.completions.create.call_args.kwargs
    assert "tools" not in kwargs
    assert "response_format" in kwargs
    assert kwargs["response_format"]["type"] == "json_object"

def test_json_object_prompt_appended_if_missing():
    adapter = GroqAdapter(config=GroqAdapterConfig(api_key="fake"), client=MagicMock())
    req = LLMRequest(
        model="qwen",
        messages=[Message(role="user", content="Hello without the J-word")],
        tools=None,
        response_schema={"type": "object", "properties": {"name": {"type": "string"}}}
    )
    
    mock_raw = MagicMock()
    mock_raw.choices[0].message.content = "{}"
    adapter._client.chat.completions.create.return_value = mock_raw
    
    adapter.complete(req)
    
    kwargs = adapter._client.chat.completions.create.call_args.kwargs
    messages = kwargs["messages"]
    assert any("json" in m["content"].lower() for m in messages)
    assert messages[-1]["role"] == "system"
    assert "valid json" in messages[-1]["content"].lower()

def test_invalid_request_400_not_transient():
    adapter = GroqAdapter(config=GroqAdapterConfig(api_key="fake"), client=MagicMock())
    
    class InvalidRequestError(Exception):
        pass
        
    adapter._client.chat.completions.create.side_effect = InvalidRequestError("400 Error")
    
    req = LLMRequest(model="qwen", messages=[Message(role="user", content="Hello")])
    with pytest.raises(LLMProviderError) as exc_info:
        adapter.complete(req)
        
    assert exc_info.value.transient is False
