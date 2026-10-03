"""SQL Query Tool for read-only access to clinical and operational data.
Implements a strict registered catalog of pre-approved parameterized queries.
"""
from typing import Any, Dict, List
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

class SqlQueryInput(BaseModel):
    query_id: str
    parameters: Dict[str, Any]
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
}

def sql_query_tool(session: Session, input_data: SqlQueryInput) -> SqlQueryOutput:
    """Execute a parameterized read-only SQL query from the approved catalog."""
    if input_data.query_id not in QUERY_CATALOG:
        return SqlQueryOutput(results=[], columns=[], error=f"Unknown query_id: {input_data.query_id}")
    
    query = QUERY_CATALOG[input_data.query_id]
    
    try:
        # Enforce row limit
        result_proxy = session.execute(query, input_data.parameters)
        keys = list(result_proxy.keys())
        rows = [dict(zip(keys, row)) for row in result_proxy.fetchmany(input_data.row_limit)]
        return SqlQueryOutput(results=rows, columns=keys)
    except Exception as e:
        return SqlQueryOutput(results=[], columns=[], error=str(e))
