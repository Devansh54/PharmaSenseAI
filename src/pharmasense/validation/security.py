import re
from pharmasense.llm.contracts import LLMProvider, LLMRequest, Message

# Heuristic prompt injection patterns
INJECTION_PATTERNS = [
    re.compile(r'ignore\s+(all\s+)?previous\s+instructions', re.IGNORECASE),
    re.compile(r'system\s+prompt', re.IGNORECASE),
    re.compile(r'you\s+are\s+now', re.IGNORECASE),
    re.compile(r'print\s+your\s+initial\s+instructions', re.IGNORECASE),
    re.compile(r'bypass', re.IGNORECASE),
    re.compile(r'drop\s+table|delete\s+from\s+[a-z_]+', re.IGNORECASE),
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
    """Uses deterministic regex matching to detect requests for direct medical advice."""
    if not query:
        return False
        
    medical_patterns = [
        re.compile(r'\b(should i take|can i take|my dosage|prescribe me|diagnose me)\b', re.IGNORECASE),
        re.compile(r'\b(what should i do for my|is this safe for my|how do i treat my)\b', re.IGNORECASE),
        re.compile(r'\b(what medication should a patient take|what medication should i take)\b', re.IGNORECASE),
        re.compile(r'\b(what should a patient take for|what should i take for)\b', re.IGNORECASE)
    ]
    
    for pattern in medical_patterns:
        if pattern.search(query):
            return True
            
    return False
