"""Structured-output parsing and validation for LLM responses."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import jsonschema

from pharmasense.llm.contracts import LLMInvalidOutputError


def parse_and_validate(content: Optional[str], schema: Optional[Dict[str, Any]]) -> Optional[Any]:
    """Parse `content` as JSON and validate it against `schema`.

    Returns None (untouched) when no `schema` was requested; plain-text
    responses are never parsed or validated. Raises
    `LLMInvalidOutputError` if a schema was requested but the content
    is missing, not valid JSON, or fails schema validation.
    """
    if schema is None:
        return None
    if content is None:
        raise LLMInvalidOutputError(
            "Structured output requested but the provider returned no content."
        )
    try:
        clean_content = content.strip()
        if clean_content.startswith("```json"):
            clean_content = clean_content[7:]
        elif clean_content.startswith("```"):
            clean_content = clean_content[3:]
        if clean_content.endswith("```"):
            clean_content = clean_content[:-3]
        clean_content = clean_content.strip()

        parsed = json.loads(clean_content)
    except json.JSONDecodeError as exc:
        raise LLMInvalidOutputError(
            f"Structured output is not valid JSON: {exc}", raw_content=content
        ) from exc
    try:
        jsonschema.validate(instance=parsed, schema=schema)
    except jsonschema.ValidationError as exc:
        raise LLMInvalidOutputError(
            f"Structured output failed schema validation: {exc.message}",
            raw_content=content,
            errors=[exc.message],
        ) from exc
    return parsed
