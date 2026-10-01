"""Provider-independent contracts for the Phase 2 LLM Gateway.

These types define the shared interface every LLM provider adapter
must implement, and the request/response shapes every caller of the
gateway uses. No provider-specific (e.g. OpenAI) types should leak
past this boundary; adapters translate to/from these contracts.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

Role = str  # "system" | "user" | "assistant" | "tool"


@dataclass(frozen=True)
class Message:
    """A single chat message in a provider-independent shape."""

    role: Role
    content: Optional[str] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


@dataclass(frozen=True)
class ToolSpec:
    """A tool the model may call, described as a JSON-schema function."""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation requested by the model."""

    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass(frozen=True)
class Usage:
    """Token usage for a single LLM call.

    `is_estimated` is True when the provider did not report usage and
    the gateway had to fall back to a zeroed placeholder (see
    `pharmasense.llm.usage.normalize_usage`), so downstream cost/observability
    code can tell real accounting apart from a missing-data fallback.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    is_estimated: bool = False


@dataclass(frozen=True)
class CostBreakdown:
    """Cost of a single LLM call, or an explicit explanation of why the
    cost is unknown (unpriced model, missing usage) rather than a
    silent $0."""

    prompt_cost: Optional[float]
    completion_cost: Optional[float]
    total_cost: Optional[float]
    currency: str = "USD"
    pricing_known: bool = True
    note: Optional[str] = None


@dataclass(frozen=True)
class LLMRequest:
    """A provider-independent request to generate a completion."""

    messages: List[Message]
    model: str
    tools: Optional[List[ToolSpec]] = None
    tool_choice: Optional[str] = None  # "auto" | "none" | "required"
    response_schema: Optional[Dict[str, Any]] = None  # JSON schema for structured output
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """A provider-independent response.

    `usage`/`cost` are filled in (or normalized) by the gateway, not
    necessarily by the adapter. `parsed` is populated by the gateway
    only when `LLMRequest.response_schema` was set and validation
    succeeded.
    """

    content: Optional[str]
    tool_calls: List[ToolCall] = field(default_factory=list)
    usage: Optional[Usage] = None
    finish_reason: Optional[str] = None
    model: Optional[str] = None
    parsed: Optional[Any] = None
    cost: Optional[CostBreakdown] = None
    raw: Optional[Any] = None


class LLMProvider(abc.ABC):
    """Contract every provider adapter (OpenAI, others) must implement.

    Adapters own all provider-SDK-specific concerns (auth, request/
    response shape, error types) and must translate them to/from the
    contracts in this module. The gateway only ever talks to this
    interface.
    """

    @abc.abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute `request` against the provider and return a response.

        Implementations must raise `LLMTimeoutError` on timeout and
        `LLMProviderError` (with `transient` set appropriately) on
        provider/API errors, rather than leaking SDK-native exceptions.
        """
        raise NotImplementedError


# --- Errors -----------------------------------------------------------


class LLMGatewayError(Exception):
    """Base class for all gateway-raised errors."""


class LLMTimeoutError(LLMGatewayError):
    """Raised when a provider call exceeds the configured timeout."""


class LLMProviderError(LLMGatewayError):
    """Raised when the provider returns an error.

    `transient` indicates whether the gateway's retry policy should
    retry the call (e.g. rate limits, 5xx, connection errors) versus
    fail fast (e.g. auth errors, malformed requests).
    """

    def __init__(
        self,
        message: str,
        *,
        transient: bool = False,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.transient = transient
        self.cause = cause


class LLMInvalidOutputError(LLMGatewayError):
    """Raised when structured output fails schema validation.

    Never retried by the gateway's transient-retry policy: a model
    that produced malformed structured output for a given request is
    not expected to self-correct on an identical retry.
    """

    def __init__(
        self,
        message: str,
        *,
        raw_content: Optional[str] = None,
        errors: Optional[List[str]] = None,
    ) -> None:
        super().__init__(message)
        self.raw_content = raw_content
        self.errors = errors or []
