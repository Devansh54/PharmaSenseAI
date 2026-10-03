def validate_output(report: str) -> tuple[bool, str]:
    """
    Basic output validation.
    """
    if not report or not report.strip():
        return False, "Generated report is empty."
        
    if len(report) > 10000:
        return False, "Generated report exceeds maximum length."
        
    return True, ""
