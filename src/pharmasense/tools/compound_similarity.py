"""Compound Similarity Tool.
Calculates attribute-based similarity for compounds.
"""
from typing import Dict, Any, List
from pydantic import BaseModel
from decimal import Decimal

from sqlalchemy.orm import Session
from pharmasense.tools.sql_query import sql_query_tool, SqlQueryInput

class CompoundSimilarityInput(BaseModel):
    target_compound_id: str
    top_k: int = 5

class CandidateSimilarity(BaseModel):
    compared_compounds: List[str]
    overall_score: float
    coverage: float
    per_feature_contribution: Dict[str, float]

class CompoundSimilarityOutput(BaseModel):
    target_compound_id: str
    top_candidates: List[CandidateSimilarity]
    limitations: List[str]
    profile_version: str

def _compute_similarity(attrs_1: Dict[str, Any], attrs_2: Dict[str, Any]) -> CandidateSimilarity:
    comp_1_id = attrs_1.get("compound_id", "Unknown")
    comp_2_id = attrs_2.get("compound_id", "Unknown")
    compared_ids = [comp_1_id, comp_2_id]

    baseline_features = {
        "chemical_class",
        "therapeutic_area",
        "target_protein",
        "molecular_weight_da",
        "solubility_mg_ml",
        "toxicity_score"
    }
    
    all_keys = set(attrs_1.keys()).union(set(attrs_2.keys())).intersection(baseline_features)
    
    if not all_keys:
        return CandidateSimilarity(
            compared_compounds=compared_ids,
            overall_score=0.0,
            coverage=0.0,
            per_feature_contribution={}
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
        elif isinstance(val1, (int, float, Decimal)) and isinstance(val2, (int, float, Decimal)):
            v1_float = float(val1)
            v2_float = float(val2)
            max_val = max(abs(v1_float), abs(v2_float))
            if max_val == 0:
                contributions[key] = 1.0
            else:
                contributions[key] = 1.0 - (abs(v1_float - v2_float) / max_val)
        else:
            contributions[key] = 0.0 # Unsupported type

    coverage = valid_features / len(all_keys)
    overall = sum(contributions.values()) / valid_features if valid_features > 0 else 0.0

    return CandidateSimilarity(
        compared_compounds=compared_ids,
        overall_score=round(overall, 3),
        coverage=round(coverage, 3),
        per_feature_contribution={k: round(v, 3) for k, v in contributions.items()}
    )

def compound_similarity_tool(session: Session, input_data: CompoundSimilarityInput) -> CompoundSimilarityOutput:
    """Calculate attribute-based similarity and rank top candidates (not molecular structure)."""
    target_id = input_data.target_compound_id
    
    all_input = SqlQueryInput(query_id="all_compounds", parameters={})
    all_out = sql_query_tool(session, all_input)
    
    if all_out.error or not all_out.results:
        return CompoundSimilarityOutput(
            target_compound_id=target_id,
            top_candidates=[],
            limitations=["No candidates found in database."],
            profile_version="v1"
        )
        
    target_attrs = None
    # Find by ID or Name
    for c in all_out.results:
        if c.get("compound_id") == target_id or c.get("compound_name") == target_id:
            target_attrs = c
            # Update target_id to the canonical ID
            target_id = c.get("compound_id")
            break
            
    if not target_attrs:
        return CompoundSimilarityOutput(
            target_compound_id=target_id,
            top_candidates=[],
            limitations=["Target compound not found."],
            profile_version="v1"
        )
        
    candidates = []
    for candidate_attrs in all_out.results:
        if candidate_attrs.get("compound_id") == target_id:
            continue
            
        sim = _compute_similarity(target_attrs, candidate_attrs)
        if sim.overall_score > 0.0:
            candidates.append(sim)
            
    # Sort descending by score
    candidates.sort(key=lambda x: x.overall_score, reverse=True)
    
    top_candidates = candidates[:input_data.top_k]
    
    return CompoundSimilarityOutput(
        target_compound_id=target_id,
        top_candidates=top_candidates,
        limitations=[
            "Similarity is attribute-based only.",
            "Does NOT imply molecular structural similarity.",
            "Does NOT imply therapeutic equivalence."
        ],
        profile_version="v1"
    )
