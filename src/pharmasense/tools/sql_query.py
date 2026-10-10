"""SQL Query Tool for read-only access to clinical and operational data.
Implements a strict registered catalog of pre-approved parameterized queries.
"""
from typing import Any, Dict, List, Literal
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

ValidQueryId = Literal[
    "trial_summary",
    "site_enrollment",
    "lab_results_summary",
    "compound_info",
    "adverse_events_by_trial",
    "trial_enrollment_stats",
    "sites_by_trial_attributes",
    "all_compounds",
    "trials_by_compound"
]

class SqlQueryInput(BaseModel):
    query_id: ValidQueryId = Field(..., description="The ID of the pre-approved query to execute.")
    parameters: Dict[str, Any] = Field(..., description="The parameters required for the selected query. Must strictly match the query's requirements.")
    row_limit: int = 100

class SqlQueryOutput(BaseModel):
    results: List[Dict[str, Any]]
    columns: List[str]
    error: str | None = None

# Pre-approved queries
QUERY_CATALOG = {
    "trials_by_compound": text("SELECT t.trial_id, t.trial_phase, t.therapeutic_area, t.status, t.target_enrollment, t.primary_endpoint FROM clinical_trials t JOIN compounds c ON t.compound_id = c.compound_id WHERE c.compound_id = :compound_id OR c.compound_name = :compound_id"),
    "trial_summary": text("SELECT trial_id, trial_phase, therapeutic_area, status, target_enrollment FROM clinical_trials WHERE trial_id = :trial_id"),
    "site_enrollment": text("SELECT site_name, country, enrollment_count, site_status FROM trial_sites WHERE trial_id = :trial_id ORDER BY enrollment_count DESC"),
    "lab_results_summary": text("SELECT r.experiment_type, r.result_value, r.unit, r.pass_fail FROM lab_results r JOIN compounds c ON r.compound_id = c.compound_id WHERE c.compound_id = :compound_id OR c.compound_name = :compound_id ORDER BY r.result_date DESC"),
    "compound_info": text("SELECT compound_id, compound_name, chemical_class, therapeutic_area, target_protein, discovery_phase, molecular_weight_da, solubility_mg_ml, toxicity_score FROM compounds WHERE compound_id = :compound_id"),
    "adverse_events_by_trial": text("SELECT event_id, event_date, adverse_event_term, severity, seriousness, outcome FROM adverse_events WHERE trial_id = :trial_id"),
    "trial_enrollment_stats": text("""
        SELECT
            t.trial_id, t.trial_phase, t.therapeutic_area, t.status, t.target_enrollment,
            COALESCE(SUM(s.enrollment_count), 0) as current_enrollment,
            CAST(COALESCE(SUM(s.enrollment_count), 0) AS FLOAT) / NULLIF(t.target_enrollment, 0) as enrollment_pct,
            CASE
                WHEN :threshold_pct IS NOT NULL THEN (CAST(COALESCE(SUM(s.enrollment_count), 0) AS FLOAT) / NULLIF(t.target_enrollment, 0)) < (:threshold_pct / 100.0)
                ELSE NULL
            END as is_below_threshold
        FROM clinical_trials t
        LEFT JOIN trial_sites s ON t.trial_id = s.trial_id
        WHERE (:trial_phase IS NULL OR t.trial_phase = :trial_phase)
          AND (:therapeutic_area IS NULL OR t.therapeutic_area = :therapeutic_area)
        GROUP BY t.trial_id, t.trial_phase, t.therapeutic_area, t.status, t.target_enrollment
    """),
    "sites_by_trial_attributes": text("""
        SELECT s.trial_id, s.site_name, s.country, s.enrollment_count, s.site_status, t.trial_phase, t.therapeutic_area
        FROM trial_sites s
        JOIN clinical_trials t ON s.trial_id = t.trial_id
        WHERE (:trial_phase IS NULL OR t.trial_phase = :trial_phase)
          AND (:therapeutic_area IS NULL OR t.therapeutic_area = :therapeutic_area)
        ORDER BY s.enrollment_count DESC
    """),
    "all_compounds": text("SELECT compound_id, compound_name, chemical_class, therapeutic_area, target_protein, discovery_phase, molecular_weight_da, solubility_mg_ml, toxicity_score FROM compounds"),
}

def sql_query_tool(session: Session, input_data: SqlQueryInput) -> SqlQueryOutput:
    """Execute a parameterized read-only SQL query from the approved catalog."""
    if input_data.query_id not in QUERY_CATALOG:
        return SqlQueryOutput(results=[], columns=[], error=f"Unknown query_id: {input_data.query_id}")

    query = QUERY_CATALOG[input_data.query_id]

    # Ensure all parameters used in the query are present in the dictionary (default to None)
    import re
    bind_params = set(re.findall(r":([a-zA-Z0-9_]+)", str(query)))

    if input_data.query_id == "trials_by_compound" and "compound_name" in input_data.parameters and "compound_id" not in input_data.parameters:
        input_data.parameters["compound_id"] = input_data.parameters.pop("compound_name")

    invalid_params = [p for p in input_data.parameters if p not in bind_params]
    if invalid_params:
        return SqlQueryOutput(
            results=[],
            columns=[],
            error=f"Invalid parameters provided: {invalid_params}. Allowed parameters for this query are: {list(bind_params)}"
        )

    safe_params = {p: None for p in bind_params}
    safe_params.update(input_data.parameters)

    try:
        # Enforce row limit
        result_proxy = session.execute(query, safe_params)
        keys = list(result_proxy.keys())
        rows = [dict(zip(keys, row)) for row in result_proxy.fetchmany(input_data.row_limit)]
        return SqlQueryOutput(results=rows, columns=keys)
    except Exception as e:
        return SqlQueryOutput(results=[], columns=[], error=str(e))
