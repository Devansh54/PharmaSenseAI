from pharmasense.llm.contracts import LLMProvider
from pharmasense.validation.security import detect_injection, detect_medical_advice

def validate_input_request(query: str, llm: LLMProvider) -> tuple[bool, str]:
    """
    Validates an incoming user request.
    Returns (is_valid, reason).
    """
    if not query or not query.strip():
        return False, "Request cannot be empty."
        
    if len(query) > 2000:
        return False, "Request is too long (limit 2000 characters)."
        
    if detect_injection(query):
        return False, "Request blocked due to security policy (prompt injection detected)."
        
    if detect_medical_advice(query, llm):
        return False, "I cannot provide personalized medical advice or prescription recommendations. Please consult a healthcare professional."
        
    return True, ""
