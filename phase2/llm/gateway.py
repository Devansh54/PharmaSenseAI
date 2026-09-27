"""Provider-independent LLM Gateway.

This is the single entry point every caller (agents, tools, etc. in
later phases) should use to talk to an LLM. All provider-specific
concerns (SDKs, auth, request/response shapes) stay behind the
`LLMProvider` adapters; callers only ever see the contracts in
`phase2.llm.contracts`.
"""
from __future__ import annotations

import logging
from typing import Optional

from phase2.config import GatewayConfig
from phase2.llm.contracts import (
    LLMGatewayError,
    LLMInvalidOutputError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
)
from phase2.llm.retry import call_with_retry
from phase2.llm.tracing import NullTracer, Tracer
from phase2.llm.usage import compute_cost, normalize_usage
from phase2.llm.validation import parse_and_validate

logger = logging.getLogger(__name__)


class LLMGateway:
    """Single governed entry point for all LLM calls.

    Per the repository guide (Step 2): "a single, swappable LLM access
    function that every agent in the system calls", with basic
    usage/cost logging on from day one.
    """

    def __init__(
        self,
        provider: LLMProvider,
        config: Optional[GatewayConfig] = None,
        tracer: Optional[Tracer] = None,
    ) -> None:
        self._provider = provider
        self._config = config or GatewayConfig()
        self._tracer = tracer or NullTracer()

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Send `request` to the configured provider and return a
        provider-independent `LLMResponse`.

        Applies bounded transient retries, normalizes/accounts for
        usage (including missing usage), computes cost, validates any
        requested structured output, and records a trace event for
        the call. Raises `LLMGatewayError` subclasses on failure.
        """
        policy = self._config.retry_policy
        event = self._tracer.start(model=request.model, metadata=dict(request.metadata))

        try:
            response = call_with_retry(lambda: self._provider.complete(request), policy)
        except LLMGatewayError as exc:
            self._tracer.end(event, error=str(exc))
            raise

        response.usage = normalize_usage(response.usage)
        response.cost = compute_cost(response.usage, request.model, pricing=self._config.pricing)

        try:
            response.parsed = parse_and_validate(response.content, request.response_schema)
        except LLMInvalidOutputError as exc:
            self._tracer.end(
                event,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_cost=response.cost.total_cost,
                tool_call_count=len(response.tool_calls),
                error=str(exc),
            )
            raise

        self._tracer.end(
            event,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_cost=response.cost.total_cost,
            tool_call_count=len(response.tool_calls),
        )
        return response
