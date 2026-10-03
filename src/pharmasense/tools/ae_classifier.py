"""Adverse Event Severity Classifier Tool.
Applies deterministic versioned rules to classify seriousness and review requirements.
"""
from pydantic import BaseModel

class AEClassifierInput(BaseModel):
    severity: str | None = None
    seriousness: str | None = None
    adverse_event_term: str | None = None

class AEClassifierOutput(BaseModel):
    severity: str | None
    seriousness: str | None
    missing_information: bool
    matched_rules: list[str]
    review_requirement: bool

def ae_severity_classifier_tool(input_data: AEClassifierInput) -> AEClassifierOutput:
    """Classify adverse event based on deterministic rules."""
    missing = False
    if not input_data.severity or not input_data.seriousness:
        missing = True
        
    rules_matched = []
    require_review = False
    
    # Rule 1: Unknown seriousness remains unknown, does not default to Non-serious.
    final_seriousness = input_data.seriousness
    
    # Rule 2: Explicitly "Serious" events trigger review
    if final_seriousness and final_seriousness.strip().lower() == "serious":
        rules_matched.append("RULE_01_SERIOUS_REQUIRES_REVIEW")
        require_review = True
        
    # Rule 3: Fatal or Life-threatening severity strongly implies Serious
    if input_data.severity and input_data.severity.strip().lower() in ["fatal", "life-threatening"]:
        rules_matched.append("RULE_02_HIGH_SEVERITY_FLAGGED")
        require_review = True
        
    return AEClassifierOutput(
        severity=input_data.severity,
        seriousness=final_seriousness,
        missing_information=missing,
        matched_rules=rules_matched,
        review_requirement=require_review
    )
