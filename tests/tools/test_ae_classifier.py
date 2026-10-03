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
        seriousness=None
    ))
    assert result.seriousness is None
    assert result.missing_information is True
    assert result.review_requirement is False

def test_ae_classifier_fatal_severity():
    result = ae_severity_classifier_tool(AEClassifierInput(
        severity="Fatal",
        seriousness="Non-serious" # Anomaly
    ))
    assert result.review_requirement is True
    assert "RULE_02_HIGH_SEVERITY_FLAGGED" in result.matched_rules
