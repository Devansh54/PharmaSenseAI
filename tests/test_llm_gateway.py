"""Tests for the Phase 2 LLM Gateway: retries, usage/cost accounting,
structured-output validation, and tool-call pass-through.

These tests never make network calls; they exercise the gateway
against a FakeProvider that implements `LLMProvider` directly.
"""
from typing import List, Union

import pytest

from pharmasense.config import GatewayConfig
from pharmasense.llm.contracts import (
    LLMInvalidOutputError,
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    Message,
    ToolCall,
    ToolSpec,
    Usage,
)
from pharmasense.llm.gateway import LLMGateway
from pharmasense.llm.retry import RetryPolicy
from pharmasense.llm.tracing import InMemoryTracer


class FakeProvider(LLMProvider):
    """Provider double that returns a scripted sequence of responses or
    exceptions, one per call, and records every request it received."""

    def __init__(self, script: List[Union[LLMResponse, Exception]]):
        self.script = list(script)
        self.calls: List[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _basic_request(**overrides) -> LLMRequest:
    defaults = dict(
        messages=[Message(role="user", content="hello")],
        model="gpt-4o-mini",
    )
    defaults.update(overrides)
    return LLMRequest(**defaults)


def _fast_policy() -> RetryPolicy:
    return RetryPolicy(max_retries=2, base_delay_seconds=0.0, max_delay_seconds=0.0, jitter_seconds=0.0)


def test_generate_success_returns_content_usage_and_cost():
    provider = FakeProvider(
        [LLMResponse(content="hi there", usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15))]
    )
    gateway = LLMGateway(provider, config=GatewayConfig(retry_policy=_fast_policy()))

    response = gateway.complete(_basic_request())

    assert response.content == "hi there"
    assert response.usage.total_tokens == 15
    assert response.cost.pricing_known is True
    assert response.cost.total_cost is not None and response.cost.total_cost > 0
    assert len(provider.calls) == 1


def test_generate_passes_through_tool_calls():
    tool_calls = [ToolCall(id="call_1", name="lookup_compound", arguments={"compound_id": "DKU-1042"})]
    provider = FakeProvider([LLMResponse(content=None, tool_calls=tool_calls, usage=Usage(10, 0, 10))])
    gateway = LLMGateway(provider, config=GatewayConfig(retry_policy=_fast_policy()))

    request = _basic_request(tools=[ToolSpec(name="lookup_compound", description="d", parameters={})])
    response = gateway.complete(request)

    assert response.tool_calls == tool_calls
    assert provider.calls[0].tools[0].name == "lookup_compound"


def test_invalid_structured_output_raises_without_retry():
    provider = FakeProvider([LLMResponse(content="not json", usage=Usage(5, 5, 10))])
    gateway = LLMGateway(provider, config=GatewayConfig(retry_policy=_fast_policy()))

    schema = {"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}}
    request = _basic_request(response_schema=schema)

    with pytest.raises(LLMInvalidOutputError):
        gateway.complete(request)
    assert len(provider.calls) == 1  # invalid output is not transient - no retry


def test_structured_output_schema_mismatch_raises():
    provider = FakeProvider([LLMResponse(content='{"answer": 42}', usage=Usage(5, 5, 10))])
    gateway = LLMGateway(provider, config=GatewayConfig(retry_policy=_fast_policy()))

    schema = {"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}}
    with pytest.raises(LLMInvalidOutputError):
        gateway.complete(_basic_request(response_schema=schema))


def test_structured_output_valid_is_parsed():
    provider = FakeProvider([LLMResponse(content='{"answer": "ok"}', usage=Usage(5, 5, 10))])
    gateway = LLMGateway(provider, config=GatewayConfig(retry_policy=_fast_policy()))

    schema = {"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}}
    response = gateway.complete(_basic_request(response_schema=schema))

    assert response.parsed == {"answer": "ok"}


def test_timeout_retries_then_succeeds():
    provider = FakeProvider([LLMTimeoutError("timed out"), LLMResponse(content="second try", usage=Usage(1, 1, 2))])
    gateway = LLMGateway(provider, config=GatewayConfig(retry_policy=_fast_policy()))

    response = gateway.complete(_basic_request())

    assert response.content == "second try"
    assert len(provider.calls) == 2


def test_timeout_retries_are_bounded_then_raise():
    provider = FakeProvider([LLMTimeoutError("t1"), LLMTimeoutError("t2"), LLMTimeoutError("t3")])
    policy = RetryPolicy(max_retries=2, base_delay_seconds=0.0, max_delay_seconds=0.0, jitter_seconds=0.0)
    gateway = LLMGateway(provider, config=GatewayConfig(retry_policy=policy))

    with pytest.raises(LLMTimeoutError):
        gateway.complete(_basic_request())
    assert len(provider.calls) == 3  # 1 initial attempt + 2 retries


def test_non_transient_provider_error_is_not_retried():
    provider = FakeProvider(
        [LLMProviderError("bad request", transient=False), LLMResponse(content="unreachable", usage=Usage(1, 1, 2))]
    )
    gateway = LLMGateway(provider, config=GatewayConfig(retry_policy=_fast_policy()))

    with pytest.raises(LLMProviderError):
        gateway.complete(_basic_request())
    assert len(provider.calls) == 1


def test_missing_usage_is_marked_estimated_and_cost_is_unknown():
    provider = FakeProvider([LLMResponse(content="no usage from provider", usage=None)])
    gateway = LLMGateway(provider, config=GatewayConfig(retry_policy=_fast_policy()))

    response = gateway.complete(_basic_request())

    assert response.usage.is_estimated is True
    assert response.usage.total_tokens == 0
    assert response.cost.total_cost is None
    assert response.cost.note == "usage_missing_from_provider"


def test_cost_for_unknown_model_is_flagged_not_zero():
    provider = FakeProvider(
        [LLMResponse(content="ok", usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150))]
    )
    gateway = LLMGateway(provider, config=GatewayConfig(retry_policy=_fast_policy()))

    response = gateway.complete(_basic_request(model="some-unpriced-model"))

    assert response.cost.pricing_known is False
    assert response.cost.total_cost is None


def test_cost_calculation_for_known_model_matches_pricing_table():
    provider = FakeProvider(
        [LLMResponse(content="ok", usage=Usage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000))]
    )
    config = GatewayConfig(
        retry_policy=_fast_policy(), pricing={"test-model": {"prompt": 0.001, "completion": 0.002}}
    )
    gateway = LLMGateway(provider, config=config)

    response = gateway.complete(_basic_request(model="test-model"))

    assert response.cost.prompt_cost == pytest.approx(0.001)
    assert response.cost.completion_cost == pytest.approx(0.002)
    assert response.cost.total_cost == pytest.approx(0.003)


def test_tracer_records_completed_call():
    provider = FakeProvider(
        [LLMResponse(content="ok", usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2))]
    )
    tracer = InMemoryTracer()
    gateway = LLMGateway(provider, config=GatewayConfig(retry_policy=_fast_policy()), tracer=tracer)

    gateway.complete(_basic_request())

    assert len(tracer.events) == 1
    assert tracer.events[0].error is None
    assert tracer.events[0].model == "gpt-4o-mini"


def test_tracer_records_error_on_exhausted_retry():
    provider = FakeProvider([LLMTimeoutError("t1"), LLMTimeoutError("t2")])
    policy = RetryPolicy(max_retries=1, base_delay_seconds=0.0, max_delay_seconds=0.0, jitter_seconds=0.0)
    tracer = InMemoryTracer()
    gateway = LLMGateway(provider, config=GatewayConfig(retry_policy=policy), tracer=tracer)

    with pytest.raises(LLMTimeoutError):
        gateway.complete(_basic_request())

    assert len(tracer.events) == 1
    assert tracer.events[0].error is not None
