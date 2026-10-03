import re
from pharmasense.llm.contracts import LLMProvider, LLMRequest, Message

# Heuristic prompt injection patterns
INJECTION_PATTERNS = [
    re.compile(r'ignore\s+(all\s+)?previous\s+instructions', re.IGNORECASE),
    re.compile(r'system\s+prompt', re.IGNORECASE),
    re.compile(r'you\s+are\s+now', re.IGNORECASE),
    re.compile(r'print\s+your\s+initial\s+instructions', re.IGNORECASE),
    re.compile(r'bypass', re.IGNORECASE),
]

def detect_injection(text: str) -> bool:
    """Returns True if the text contains obvious prompt injection patterns."""
    if not text:
        return False
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return True
    return False

def detect_medical_advice(query: str, llm: LLMProvider) -> bool:
    """Uses a lightweight LLM call to semantically detect requests for direct medical advice."""
    prompt = f"""
You are a medical safety classifier. Your job is to determine if the user is asking for personalized medical advice, prescription recommendations, or a diagnosis.

General pharmaceutical research questions (e.g. "What are the adverse effects of drug X?", "How does compound Y work?") are NOT medical advice and should be allowed.
Questions like "Should I take drug X?", "What should I do for my headache?", or "Is this safe for my condition?" are medical advice and should be blocked.

User Query:
{query}

Respond strictly with a JSON object: {{"is_medical_advice": true}} or {{"is_medical_advice": false}}.
"""
    schema = {
        "type": "object",
        "properties": {
            "is_medical_advice": {"type": "boolean"}
        },
        "required": ["is_medical_advice"],
        "additionalProperties": False
    }
    
    req = LLMRequest(
        model="gpt-4.1-mini",
        messages=[Message(role="user", content=prompt)],
        response_schema=schema,
        temperature=0.0
    )
    
    try:
        resp = llm.complete(req)
        import json
        data = json.loads(resp.content)
        return data.get("is_medical_advice", False)
    except Exception:
        # In case of LLM failure, fail safe or fail open?
        # A safety classifier should default to False if we don't want to break the app,
        # but let's assume False to allow normal queries if the safety check crashes.
        return False
