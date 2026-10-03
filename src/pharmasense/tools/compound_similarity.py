"""Compound Similarity Tool.
Calculates attribute-based similarity for compounds.
"""
from typing import Dict, Any, List
from pydantic import BaseModel

class CompoundSimilarityInput(BaseModel):
    compound_1_attrs: Dict[str, Any]
    compound_2_attrs: Dict[str, Any]

class CompoundSimilarityOutput(BaseModel):
    overall_score: float
    coverage: float
    per_feature_contribution: Dict[str, float]
    limitations: List[str]
    profile_version: str

def compound_similarity_tool(input_data: CompoundSimilarityInput) -> CompoundSimilarityOutput:
    """Calculate attribute-based similarity (not molecular structure)."""
    attrs_1 = input_data.compound_1_attrs
    attrs_2 = input_data.compound_2_attrs
    
    all_keys = set(attrs_1.keys()).union(set(attrs_2.keys()))
    if not all_keys:
        return CompoundSimilarityOutput(
            overall_score=0.0,
            coverage=0.0,
            per_feature_contribution={},
            limitations=["No attributes provided for comparison."],
            profile_version="v1"
        )
        
    contributions = {}
    valid_features = 0
    
    for key in all_keys:
        val1 = attrs_1.get(key)
        val2 = attrs_2.get(key)
        
        if val1 is None or val2 is None:
            continue
            
        valid_features += 1
        
        # Categorical Match
        if isinstance(val1, str) and isinstance(val2, str):
            contributions[key] = 1.0 if val1.lower() == val2.lower() else 0.0
        # Numeric distance
        elif isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
            max_val = max(abs(val1), abs(val2))
            if max_val == 0:
                contributions[key] = 1.0
            else:
                contributions[key] = 1.0 - (abs(val1 - val2) / max_val)
        else:
            contributions[key] = 0.0 # Unsupported type
            
    coverage = valid_features / len(all_keys)
    overall = sum(contributions.values()) / valid_features if valid_features > 0 else 0.0
    
    return CompoundSimilarityOutput(
        overall_score=round(overall, 3),
        coverage=round(coverage, 3),
        per_feature_contribution={k: round(v, 3) for k, v in contributions.items()},
        limitations=[
            "Similarity is attribute-based only.",
            "Does NOT imply molecular structural similarity.",
            "Does NOT imply therapeutic equivalence."
        ],
        profile_version="v1"
    )
