"""Tests for AE Severity Classifier tool."""
from pharmasense.tools.ae_classifier import ae_severity_classifier_tool, AEClassifierInput

def test_ae_classifier_serious_requires_review():
    result = ae_severity_classifier_tool(AEClassifierInput(
        severity="Moderate",
        seriousness="Serious"
    ))
    assert result.review_requirement is True
    assert "RULE_01_SERIOUS_REQUIRES_REVIEW" in result.matched_rules

def test_ae_classifier_unknown_seriousness():
    result = ae_severity_classifier_tool(AEClassifierInput(
        severity="Mild",
        seriousness="Unknown"
    ))
    assert result.seriousness == "Unknown"
    assert result.missing_information is True
    assert result.review_requirement is False

def test_ae_classifier_fatal_severity():
    result = ae_severity_classifier_tool(AEClassifierInput(
        severity="Fatal",
        seriousness="Non-serious" # Anomaly
    ))
    assert result.review_requirement is True
    assert "RULE_02_HIGH_SEVERITY_FLAGGED" in result.matched_rules

def test_classifier_schema_unambiguous():
    """Proves the actual tool schema exposed to Groq is unambiguous and correctly typed (Test B)."""
    schema = AEClassifierInput.model_json_schema()
    # It must not use anyOf, it must be type: string.
    assert schema["properties"]["severity"]["type"] == "string"
    assert "anyOf" not in schema["properties"]["severity"]

def test_classifier_malformed_arguments_rejected():
    """Proves malformed classifier arguments are rejected cleanly (Test C)."""
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        # Passing an array instead of string
        AEClassifierInput(severity=["Mild"], seriousness="Serious", adverse_event_term="Headache")
