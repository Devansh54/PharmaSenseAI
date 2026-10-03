import re
from typing import List

from pharmasense.llm.contracts import Message

# Regex for common PII patterns
PII_PATTERNS = [
    # SSN: XXX-XX-XXXX
    re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    # Phone numbers (US format)
    re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),
    # Email addresses
    re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'),
    # Mock Patient IDs (e.g. PT-12345)
    re.compile(r'\bPT-\d{5}\b'),
]

def scrub_text(text: str) -> str:
    if not text:
        return text
    scrubbed = text
    for pattern in PII_PATTERNS:
        scrubbed = pattern.sub("[REDACTED_PII]", scrubbed)
    return scrubbed

def scrub_messages(messages: List[Message]) -> List[Message]:
    """Scrub PII from outgoing LLM messages."""
    scrubbed_messages = []
    for msg in messages:
        # Create a shallow copy to modify content safely
        new_msg = Message(
            role=msg.role,
            content=scrub_text(msg.content) if msg.content else msg.content,
            name=msg.name,
            tool_calls=msg.tool_calls,
            tool_call_id=msg.tool_call_id
        )
        scrubbed_messages.append(new_msg)
    return scrubbed_messages
