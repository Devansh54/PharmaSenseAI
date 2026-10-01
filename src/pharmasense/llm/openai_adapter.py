"""Configurable OpenAI SDK adapter.

Translates the provider-independent `LLMRequest`/`LLMResponse`
contracts to and from the `openai` Python SDK's chat completions API.
This is the only module in Phase 2 allowed to import the `openai`
package; every other module talks through `pharmasense.llm.contracts`.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from pharmasense.config import OpenAIAdapterConfig
from pharmasense.llm.contracts import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    Message,
    ToolCall,
    Usage,
)

logger = logging.getLogger(__name__)

try:
    import openai
except ImportError:  # pragma: no cover - exercised only when openai isn't installed
    openai = None  # type: ignore[assignment]

# SDK exception class names that should be treated as transient
# (safe to retry) vs. non-transient (fail fast). Matched by name rather
# than `isinstance` against `openai.*` so this adapter keeps working
# across SDK versions that rename/reshuffle their exception hierarchy.
_TIMEOUT_EXCEPTION_NAMES = {"APITimeoutError", "Timeout"}
_TRANSIENT_EXCEPTION_NAMES = {
    "RateLimitError",
    "APIConnectionError",
    "InternalServerError",
    "ServiceUnavailableError",
}
_NON_TRANSIENT_EXCEPTION_NAMES = {
    "AuthenticationError",
    "PermissionDeniedError",
    "BadRequestError",
    "NotFoundError",
    "InvalidRequestError",
    "UnprocessableEntityError",
}


def _require_openai() -> None:
    if openai is None:  # pragma: no cover
        raise LLMProviderError(
            "The 'openai' package is required to use OpenAIAdapter. "
            "Install it via requirements.txt.",
            transient=False,
        )


def _to_openai_messages(messages: List[Message]) -> List[Dict[str, Any]]:
    payload = []
    for m in messages:
        entry: Dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_call_id:
            entry["tool_call_id"] = m.tool_call_id
        if m.name:
            entry["name"] = m.name
        payload.append(entry)
    return payload


def _to_openai_tools(request: LLMRequest) -> Optional[List[Dict[str, Any]]]:
    if not request.tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters or {"type": "object", "properties": {}},
            },
        }
        for t in request.tools
    ]


def _to_openai_response_format(request: LLMRequest) -> Optional[Dict[str, Any]]:
    if not request.response_schema:
        return None
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "structured_output",
            "schema": request.response_schema,
            "strict": True,
        },
    }


def _parse_tool_calls(message: Any) -> List[ToolCall]:
    raw_calls = getattr(message, "tool_calls", None) or []
    calls: List[ToolCall] = []
    for c in raw_calls:
        try:
            args = json.loads(c.function.arguments) if c.function.arguments else {}
        except json.JSONDecodeError:
            args = {"_raw": c.function.arguments}
        calls.append(ToolCall(id=c.id, name=c.function.name, arguments=args))
    return calls


def _parse_usage(raw_usage: Any) -> Optional[Usage]:
    if raw_usage is None:
        return None
    prompt = getattr(raw_usage, "prompt_tokens", None)
    completion = getattr(raw_usage, "completion_tokens", None)
    total = getattr(raw_usage, "total_tokens", None)
    if prompt is None and completion is None and total is None:
        return None
    return Usage(
        prompt_tokens=prompt or 0,
        completion_tokens=completion or 0,
        total_tokens=total if total is not None else (prompt or 0) + (completion or 0),
        is_estimated=False,
    )


class OpenAIAdapter(LLMProvider):
    """LLMProvider backed by the OpenAI Chat Completions API.

    Configuration (API key, base URL, org, model, timeout) is fully
    externalized via `OpenAIAdapterConfig`, so this adapter works
    unchanged against OpenAI or any OpenAI-compatible endpoint.
    """

    def __init__(
        self,
        config: Optional[OpenAIAdapterConfig] = None,
        client: Optional[Any] = None,
    ) -> None:
        self._config = config or OpenAIAdapterConfig()
        if client is not None:
            self._client = client
        else:
            _require_openai()
            self._client = openai.OpenAI(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
                organization=self._config.organization,
                timeout=self._config.timeout_seconds,
            )

    def complete(self, request: LLMRequest) -> LLMResponse:
        params: Dict[str, Any] = {
            "model": request.model or self._config.model,
            "messages": _to_openai_messages(request.messages),
        }
        tools = _to_openai_tools(request)
        if tools:
            params["tools"] = tools
            params["tool_choice"] = request.tool_choice or "auto"
        response_format = _to_openai_response_format(request)
        if response_format:
            params["response_format"] = response_format
        if request.temperature is not None:
            params["temperature"] = request.temperature
        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens

        try:
            raw = self._client.chat.completions.create(**params)
        except Exception as exc:
            raise self._translate_error(exc) from exc

        choice = raw.choices[0]
        message = choice.message
        return LLMResponse(
            content=getattr(message, "content", None),
            tool_calls=_parse_tool_calls(message),
            usage=_parse_usage(getattr(raw, "usage", None)),
            finish_reason=getattr(choice, "finish_reason", None),
            model=getattr(raw, "model", params["model"]),
            raw=raw,
        )

    @staticmethod
    def _translate_error(exc: Exception) -> Exception:
        """Map SDK exceptions to gateway contracts by class name.

        Matching by name (rather than importing every `openai.*`
        exception class) keeps this adapter working across SDK
        minor-version changes without a hard-pinned dependency on
        exact exception locations.
        """
        name = type(exc).__name__
        if name in _TIMEOUT_EXCEPTION_NAMES:
            return LLMTimeoutError(str(exc))
        if name in _TRANSIENT_EXCEPTION_NAMES:
            return LLMProviderError(str(exc), transient=True, cause=exc)
        if name in _NON_TRANSIENT_EXCEPTION_NAMES:
            return LLMProviderError(str(exc), transient=False, cause=exc)
        return LLMProviderError(str(exc), transient=False, cause=exc)
