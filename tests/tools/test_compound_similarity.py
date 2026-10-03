"""Tests for Compound Similarity tool."""
from pharmasense.tools.compound_similarity import compound_similarity_tool, CompoundSimilarityInput

def test_compound_similarity_identical():
    attrs = {"chemical_class": "Kinase Inhibitor", "molecular_weight_da": 500}
    result = compound_similarity_tool(CompoundSimilarityInput(
        compound_1_attrs=attrs,
        compound_2_attrs=attrs
    ))
    assert result.overall_score == 1.0
    assert result.coverage == 1.0

def test_compound_similarity_partial():
    attrs1 = {"chemical_class": "Kinase Inhibitor", "molecular_weight_da": 500}
    attrs2 = {"chemical_class": "Protease Inhibitor", "molecular_weight_da": 250}
    result = compound_similarity_tool(CompoundSimilarityInput(
        compound_1_attrs=attrs1,
        compound_2_attrs=attrs2
    ))
    assert result.coverage == 1.0
    # Class is 0, weight is 1.0 - (250/500) = 0.5. Average = 0.25
    assert result.overall_score == 0.25
    assert result.per_feature_contribution["chemical_class"] == 0.0
    assert result.per_feature_contribution["molecular_weight_da"] == 0.5
