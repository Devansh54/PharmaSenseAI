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
    "trial_enrollment_stats"
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
    "trial_summary": text("SELECT trial_id, trial_phase, therapeutic_area, status, target_enrollment FROM clinical_trials WHERE trial_id = :trial_id"),
    "site_enrollment": text("SELECT site_name, country, enrollment_count, site_status FROM trial_sites WHERE trial_id = :trial_id ORDER BY enrollment_count DESC"),
    "lab_results_summary": text("SELECT experiment_type, result_value, unit, pass_fail FROM lab_results WHERE compound_id = :compound_id ORDER BY result_date DESC"),
    "compound_info": text("SELECT compound_name, chemical_class, target_protein, discovery_phase FROM compounds WHERE compound_id = :compound_id"),
    "adverse_events_by_trial": text("SELECT event_date, adverse_event_term, severity, seriousness, outcome FROM adverse_events WHERE trial_id = :trial_id"),
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
}

def sql_query_tool(session: Session, input_data: SqlQueryInput) -> SqlQueryOutput:
    """Execute a parameterized read-only SQL query from the approved catalog."""
    if input_data.query_id not in QUERY_CATALOG:
        return SqlQueryOutput(results=[], columns=[], error=f"Unknown query_id: {input_data.query_id}")

    query = QUERY_CATALOG[input_data.query_id]

    # Ensure all parameters used in the query are present in the dictionary (default to None)
    import re
    bind_params = re.findall(r":([a-zA-Z0-9_]+)", str(query))
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
