"""Configurable Gemini SDK adapter.

Translates the provider-independent `LLMRequest`/`LLMResponse`
contracts to and from the `google-genai` Python SDK.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from pharmasense.config import GeminiAdapterConfig
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
    import google.genai as genai
    from google.genai import types
except ImportError:  # pragma: no cover
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]

def _require_gemini() -> None:
    if genai is None:  # pragma: no cover
        raise LLMProviderError(
            "The 'google-genai' package is required to use GeminiAdapter. "
            "Install it via pyproject.toml / uv.",
            transient=False,
        )

def _to_gemini_messages(messages: List[Message]) -> List[types.Content]:
    contents = []

    current_tool_parts = []

    def flush_tools():
        if current_tool_parts:
            contents.append(types.Content(role="user", parts=current_tool_parts.copy()))
            current_tool_parts.clear()

    for m in messages:
        if m.role == "system":
            continue

        role = "model" if m.role == "assistant" else "user"

        if m.role == "tool" and m.name:
            try:
                response_dict = json.loads(m.content) if m.content else {}
            except json.JSONDecodeError:
                response_dict = {"result": m.content}

            part = types.Part.from_function_response(name=m.name, response=response_dict)
            current_tool_parts.append(part)
            continue

        flush_tools()

        if m.role == "assistant" and getattr(m, "provider_metadata", None):
            contents.append(types.Content(role=role, parts=m.provider_metadata))
            continue

        parts = []
        if m.content:
            parts.append(types.Part.from_text(text=m.content))

        if m.tool_calls:
            for tc in m.tool_calls:
                parts.append(types.Part.from_function_call(name=tc.name, args=tc.arguments))

        contents.append(types.Content(role=role, parts=parts))

    flush_tools()

    # Coalesce consecutive roles of the same type if they exist, though typically function responses
    # handled above are the main cause. Gemini requires strict alternating user/model.
    coalesced = []
    for c in contents:
        if not coalesced:
            coalesced.append(c)
        elif coalesced[-1].role == c.role:
            coalesced[-1].parts.extend(c.parts)
        else:
            coalesced.append(c)

    return coalesced

def _extract_system_instruction(messages: List[Message]) -> Optional[str]:
    system_parts = [m.content for m in messages if m.role == "system" and m.content]
    if system_parts:
        return "\n".join(system_parts)
    return None

def _to_gemini_tools(request: LLMRequest) -> Optional[List[types.Tool]]:
    if not request.tools:
        return None

    function_declarations = []
    for t in request.tools:
        # Convert JSON schema to Gemini Schema
        func_decl = types.FunctionDeclaration(
            name=t.name,
            description=t.description,
        )
        if t.parameters:
            func_decl.parameters = _sanitize_schema_for_gemini(t.parameters)
        function_declarations.append(func_decl)

    return [types.Tool(function_declarations=function_declarations)]

def _parse_usage(usage_metadata: Any) -> Optional[Usage]:
    if not usage_metadata:
        return None

    prompt = getattr(usage_metadata, "prompt_token_count", 0)
    completion = getattr(usage_metadata, "candidates_token_count", 0)
    total = getattr(usage_metadata, "total_token_count", prompt + completion)

    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        is_estimated=False
    )

def _parse_tool_calls(parts: Any) -> List[ToolCall]:
    calls = []
    if not parts:
        return calls

    for p in parts:
        if p.function_call:
            import uuid
            calls.append(ToolCall(
                id=f"call_{uuid.uuid4().hex[:8]}", # Gemini doesn't always provide explicit IDs for tool calls in the same way, generating one.
                name=p.function_call.name,
                arguments=p.function_call.args
            ))
    return calls

def _sanitize_schema_for_gemini(schema: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(schema, dict):
        return schema
    clean = {}
    for k, v in schema.items():
        if k in ("additionalProperties", "title", "default"):
            continue
        if isinstance(v, dict):
            clean[k] = _sanitize_schema_for_gemini(v)
        elif isinstance(v, list):
            clean[k] = [_sanitize_schema_for_gemini(i) if isinstance(i, dict) else i for i in v]
        else:
            clean[k] = v
    return clean

class GeminiAdapter(LLMProvider):
    """LLMProvider backed by the Google GenAI SDK."""

    def __init__(self, config: Optional[GeminiAdapterConfig] = None):
        _require_gemini()
        self._config = config or GeminiAdapterConfig()
        # The new SDK uses Client
        self._client = genai.Client(api_key=self._config.api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        from pharmasense.validation.pii import scrub_messages
        scrubbed_messages = scrub_messages(request.messages)

        contents = _to_gemini_messages(scrubbed_messages)
        system_instruction = _extract_system_instruction(scrubbed_messages)

        model_name = request.model or self._config.model

        config_kwargs = {}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if request.temperature is not None:
            config_kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            config_kwargs["max_output_tokens"] = request.max_tokens

        tools = _to_gemini_tools(request)
        if tools:
            config_kwargs["tools"] = tools

        if request.response_schema:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = _sanitize_schema_for_gemini(request.response_schema)

        gen_config = types.GenerateContentConfig(**config_kwargs)

        try:
            raw = self._client.models.generate_content(
                model=model_name,
                contents=contents,
                config=gen_config
            )
        except Exception as exc:
            raise self._translate_error(exc) from exc

        # Parse response
        content = None
        tool_calls = []
        finish_reason = None
        raw_parts = None

        if raw.candidates:
            candidate = raw.candidates[0]
            if candidate.content and candidate.content.parts:
                parts = candidate.content.parts
                raw_parts = parts

                # Tool calls
                tool_calls = _parse_tool_calls(parts)

                # Text content
                text_parts = [p.text for p in parts if getattr(p, "text", None)]
                if text_parts:
                    content = "".join(text_parts)
                elif not tool_calls:
                    # Fallback: when response_mime_type=application/json is used,
                    # some SDK versions surface the structured JSON via response.text
                    # rather than through candidate.content.parts[].text.
                    # Only do this if there are no tool calls, to avoid SDK warnings for function_call parts.
                    top_text = getattr(raw, "text", None)
                    if top_text:
                        content = top_text

            if getattr(candidate, "finish_reason", None):
                finish_reason = candidate.finish_reason.name
        else:
            # No candidates — last resort: try raw.text (can occur with some SDK versions)
            top_text = getattr(raw, "text", None)
            if top_text:
                content = top_text

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=_parse_usage(getattr(raw, "usage_metadata", None)),
            finish_reason=finish_reason,
            model=model_name,
            raw=raw,
            provider_metadata=raw_parts
        )

    @staticmethod
    def _translate_error(exc: Exception) -> Exception:
        name = type(exc).__name__
        if "Timeout" in name:
            return LLMTimeoutError(str(exc))
        if "APIError" in name or "InternalServerError" in name:
             return LLMProviderError(str(exc), transient=True, cause=exc)
        return LLMProviderError(str(exc), transient=False, cause=exc)
