import re
from pharmasense.llm.contracts import LLMProvider, LLMRequest, Message
from pharmasense.config import DEFAULT_MODEL

def check_citations_exist(report: str) -> bool:
    """
    Deterministic check: ensures that if citations like [1] exist, 
    they are correctly formatted. In a fuller implementation, this would
    check against the specific returned context chunks. For now, it ensures
    at least no naked empty brackets or invalid citation forms.
    """
    # This is a stub for deterministic checking. True means passed.
    if "[]" in report:
        return False
    return True

def validate_evidence(report: str, context_summary: str, llm: LLMProvider) -> tuple[bool, str]:
    """
    Uses an LLM to semantically verify if the claims in the report are supported
    by the provided context.
    Returns (is_valid, reason/feedback).
    """
    if not check_citations_exist(report):
        return False, "Formatting error: Invalid citations found."
        
    prompt = f"""
You are an evidence validation judge. 
Your task is to determine if the claims made in the REPORT are fully supported by the CONTEXT.
If the report makes claims that are NOT in the context, or hallucinates facts, fail it.

CONTEXT:
{context_summary}

REPORT:
{report}

Respond strictly with a JSON object: 
{{"is_supported": true/false, "reason": "explanation of what is unsupported if false"}}
"""
    schema = {
        "type": "object",
        "properties": {
            "is_supported": {"type": "boolean"},
            "reason": {"type": "string"}
        },
        "required": ["is_supported", "reason"],
        "additionalProperties": False
    }
    
    req = LLMRequest(
        model=DEFAULT_MODEL,
        messages=[Message(role="user", content=prompt)],
        response_schema=schema,
        temperature=0.0
    )
    
    try:
        resp = llm.complete(req)
        import json
        data = json.loads(resp.content)
        is_supported = data.get("is_supported", True)
        reason = data.get("reason", "")
        return is_supported, reason
    except Exception:
        # In case of failure, assume it's unsupported for safety.
        return False, "Evidence validation failed due to internal error."
