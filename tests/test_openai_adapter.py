"""Tests for the OpenAI SDK adapter's request/response translation.

A fake OpenAI client double is injected so these tests never hit the
network or require the `openai` package/credentials to be installed.
"""
import json
from types import SimpleNamespace

import pytest

from phase2.config import OpenAIAdapterConfig
from phase2.llm.contracts import LLMProviderError, LLMRequest, LLMTimeoutError, Message, ToolSpec
from phase2.llm.openai_adapter import OpenAIAdapter


class _FakeCompletions:
    def __init__(self, response=None, exception=None):
        self._response = response
        self._exception = exception
        self.received_params = None

    def create(self, **params):
        self.received_params = params
        if self._exception is not None:
            raise self._exception
        return self._response


class _FakeClient:
    def __init__(self, response=None, exception=None):
        self.chat = SimpleNamespace(completions=_FakeCompletions(response, exception))


def _fake_response(content="hi", tool_calls=None, usage=(10, 5, 15)):
    message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage_obj = (
        SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1], total_tokens=usage[2])
        if usage
        else None
    )
    return SimpleNamespace(choices=[choice], usage=usage_obj, model="gpt-4o-mini")


def _request(**overrides):
    defaults = dict(messages=[Message(role="user", content="hello")], model="gpt-4o-mini")
    defaults.update(overrides)
    return LLMRequest(**defaults)


def test_complete_parses_content_and_usage():
    client = _FakeClient(response=_fake_response(content="hello back"))
    adapter = OpenAIAdapter(config=OpenAIAdapterConfig(api_key="x"), client=client)

    response = adapter.complete(_request())

    assert response.content == "hello back"
    assert response.usage.prompt_tokens == 10
    assert response.usage.completion_tokens == 5
    assert response.finish_reason == "stop"


def test_complete_sends_tools_when_present():
    client = _FakeClient(response=_fake_response())
    adapter = OpenAIAdapter(config=OpenAIAdapterConfig(api_key="x"), client=client)
    tool = ToolSpec(name="lookup", description="d", parameters={"type": "object"})

    adapter.complete(_request(tools=[tool]))

    sent = client.chat.completions.received_params
    assert sent["tools"][0]["function"]["name"] == "lookup"
    assert sent["tool_choice"] == "auto"


def test_complete_parses_tool_calls_from_response():
    function = SimpleNamespace(name="lookup", arguments=json.dumps({"id": "DKU-1042"}))
    tool_call = SimpleNamespace(id="call_1", function=function)
    client = _FakeClient(response=_fake_response(content=None, tool_calls=[tool_call]))
    adapter = OpenAIAdapter(config=OpenAIAdapterConfig(api_key="x"), client=client)

    response = adapter.complete(_request())

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "lookup"
    assert response.tool_calls[0].arguments == {"id": "DKU-1042"}


def test_complete_returns_no_usage_when_provider_omits_it():
    client = _FakeClient(response=_fake_response(usage=None))
    adapter = OpenAIAdapter(config=OpenAIAdapterConfig(api_key="x"), client=client)

    response = adapter.complete(_request())

    assert response.usage is None  # the gateway's normalize_usage() handles this


def test_complete_translates_timeout_error():
    class APITimeoutError(Exception):
        pass

    client = _FakeClient(exception=APITimeoutError("timed out"))
    adapter = OpenAIAdapter(config=OpenAIAdapterConfig(api_key="x"), client=client)

    with pytest.raises(LLMTimeoutError):
        adapter.complete(_request())


def test_complete_translates_rate_limit_error_as_transient():
    class RateLimitError(Exception):
        pass

    client = _FakeClient(exception=RateLimitError("slow down"))
    adapter = OpenAIAdapter(config=OpenAIAdapterConfig(api_key="x"), client=client)

    with pytest.raises(LLMProviderError) as exc_info:
        adapter.complete(_request())
    assert exc_info.value.transient is True


def test_complete_translates_authentication_error_as_non_transient():
    class AuthenticationError(Exception):
        pass

    client = _FakeClient(exception=AuthenticationError("bad key"))
    adapter = OpenAIAdapter(config=OpenAIAdapterConfig(api_key="x"), client=client)

    with pytest.raises(LLMProviderError) as exc_info:
        adapter.complete(_request())
    assert exc_info.value.transient is False


def test_complete_sends_response_format_for_structured_output():
    client = _FakeClient(response=_fake_response(content='{"answer": "ok"}'))
    adapter = OpenAIAdapter(config=OpenAIAdapterConfig(api_key="x"), client=client)
    schema = {"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}}

    adapter.complete(_request(response_schema=schema))

    sent = client.chat.completions.received_params
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["schema"] == schema
