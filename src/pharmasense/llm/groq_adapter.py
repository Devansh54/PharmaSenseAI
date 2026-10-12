"""Configurable Groq SDK adapter.

Translates the provider-independent `LLMRequest`/`LLMResponse`
contracts to and from the `groq` Python SDK.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from pharmasense.config import GroqAdapterConfig
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
    import groq
except ImportError:  # pragma: no cover
    groq = None  # type: ignore[assignment]

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


def _require_groq() -> None:
    if groq is None:  # pragma: no cover
        raise LLMProviderError(
            "The 'groq' package is required to use GroqAdapter. "
            "Install it via pyproject.toml / uv.",
            transient=False,
        )


def _to_groq_messages(messages: List[Message]) -> List[Dict[str, Any]]:
    payload = []
    for m in messages:
        entry: Dict[str, Any] = {"role": m.role, "content": m.content or ""}
        if m.tool_call_id:
            entry["tool_call_id"] = m.tool_call_id
        if m.name:
            entry["name"] = m.name
        if m.tool_calls:
            calls_list = []
            for tc in m.tool_calls:
                # If we failed to parse arguments earlier (e.g., model returned invalid JSON)
                # do not send invalid JSON back to Groq in the history, as Groq validates
                # history strictly and will return HTTP 422. Use empty dict as fallback.
                if "_raw" in tc.arguments:
                    args_str = "{}"
                else:
                    args_str = json.dumps(tc.arguments)
                    
                calls_list.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": args_str}
                })
            entry["tool_calls"] = calls_list
        payload.append(entry)
    return payload


def _to_groq_tools(request: LLMRequest) -> Optional[List[Dict[str, Any]]]:
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


def _to_groq_response_format(request: LLMRequest) -> Optional[Dict[str, Any]]:
    if not request.response_schema:
        return None
    # Current Groq allows json_object natively without strict json_schema issues
    return {"type": "json_object"}


def _parse_tool_calls(message: Any) -> List[ToolCall]:
    raw_calls = getattr(message, "tool_calls", None) or []
    calls: List[ToolCall] = []
    for c in raw_calls:
        if not c.function.arguments:
            args = {}
        else:
            clean_args = c.function.arguments.strip()
            if clean_args.startswith("```json"):
                clean_args = clean_args[7:]
            elif clean_args.startswith("```"):
                clean_args = clean_args[3:]
            if clean_args.endswith("```"):
                clean_args = clean_args[:-3]
            clean_args = clean_args.strip()
            
            try:
                args = json.loads(clean_args) if clean_args else {}
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


class GroqAdapter(LLMProvider):
    """LLMProvider backed by the Groq API."""

    def __init__(
        self,
        config: Optional[GroqAdapterConfig] = None,
        client: Optional[Any] = None,
    ) -> None:
        self._config = config or GroqAdapterConfig()
        if client is not None:
            self._client = client
        else:
            _require_groq()
            self._client = groq.Groq(
                api_key=self._config.api_key,
                timeout=self._config.timeout_seconds,
            )

    def complete(self, request: LLMRequest) -> LLMResponse:
        from pharmasense.validation.pii import scrub_messages
        scrubbed_messages = scrub_messages(request.messages)
        params: Dict[str, Any] = {
            "model": request.model or self._config.model,
            "messages": _to_groq_messages(scrubbed_messages),
        }
        tools = _to_groq_tools(request)
        if tools:
            params["tools"] = tools
            params["tool_choice"] = request.tool_choice or "auto"
        else:
            response_format = _to_groq_response_format(request)
            if response_format:
                params["response_format"] = response_format

        if request.response_schema:
            schema_str = json.dumps(request.response_schema)
            msg = "When you provide your final response (instead of calling a tool), you must output strictly in valid JSON format adhering to this schema" if tools else "Please output strictly in valid JSON format adhering to this schema"
            params["messages"].append({
                "role": "system",
                "content": f"{msg}: {schema_str}"
            })

        if request.temperature is not None:
            params["temperature"] = request.temperature
        max_tokens = request.max_tokens if request.max_tokens is not None else getattr(self._config, "max_output_tokens", 600)
        if max_tokens is not None:
            params["max_tokens"] = max_tokens

        try:
            raw = self._client.chat.completions.create(**params)
        except Exception as exc:
            raise self._translate_error(exc) from exc

        choice = raw.choices[0]
        message = choice.message
        # DEBUG
        print("DEBUG GROQ CONTENT:", getattr(message, "content", None))
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
        name = type(exc).__name__
        if name in _TIMEOUT_EXCEPTION_NAMES:
            return LLMTimeoutError(str(exc))
        if name in _TRANSIENT_EXCEPTION_NAMES:
            return LLMProviderError(str(exc), transient=True, cause=exc)
        if name in _NON_TRANSIENT_EXCEPTION_NAMES:
            return LLMProviderError(str(exc), transient=False, cause=exc)
        return LLMProviderError(str(exc), transient=False, cause=exc)
