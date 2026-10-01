"""Expected schema definitions for the 7 baseline CSVs.

`dtype` uses simple logical kinds: str, int, float, date, datetime, bool.
These definitions are the single source of truth used by the audit,
the Postgres/Alembic schema, and the ingestion coercion logic.
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class ForeignKey:
    column: str
    ref_table: str
    ref_column: str
    nullable: bool = False


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: Dict[str, str]
    primary_key: str
    required_columns: List[str]
    foreign_keys: List[ForeignKey] = field(default_factory=list)


SCHEMAS: Dict[str, TableSchema] = {
    "compounds": TableSchema(
        name="compounds",
        columns={
            "compound_id": "str",
            "compound_name": "str",
            "chemical_class": "str",
            "therapeutic_area": "str",
            "target_protein": "str",
            "mechanism_of_action": "str",
            "discovery_phase": "str",
            "molecular_weight_da": "float",
            "solubility_mg_ml": "float",
            "toxicity_score": "float",
            "lead_scientist": "str",
            "synthesis_date": "date",
            "created_at": "date",
        },
        primary_key="compound_id",
        required_columns=["compound_id", "compound_name"],
    ),
    "clinical_trials": TableSchema(
        name="clinical_trials",
        columns={
            "trial_id": "str",
            "compound_id": "str",
            "trial_phase": "str",
            "therapeutic_area": "str",
            "sponsor": "str",
            "start_date": "date",
            "planned_end_date": "date",
            "actual_end_date": "date",
            "status": "str",
            "target_enrollment": "int",
            "actual_enrollment": "int",
            "primary_endpoint": "str",
        },
        primary_key="trial_id",
        required_columns=["trial_id", "compound_id"],
        foreign_keys=[ForeignKey("compound_id", "compounds", "compound_id")],
    ),
    "trial_sites": TableSchema(
        name="trial_sites",
        columns={
            "site_id": "str",
            "trial_id": "str",
            "site_name": "str",
            "country": "str",
            "principal_investigator": "str",
            "enrollment_count": "int",
            "site_status": "str",
        },
        primary_key="site_id",
        required_columns=["site_id", "trial_id"],
        foreign_keys=[ForeignKey("trial_id", "clinical_trials", "trial_id")],
    ),
    "lab_results": TableSchema(
        name="lab_results",
        columns={
            "result_id": "str",
            "compound_id": "str",
            "experiment_type": "str",
            "result_value": "float",
            "unit": "str",
            "result_date": "date",
            "technician": "str",
            "pass_fail": "str",
        },
        primary_key="result_id",
        required_columns=["result_id", "compound_id"],
        foreign_keys=[ForeignKey("compound_id", "compounds", "compound_id")],
    ),
    "adverse_events": TableSchema(
        name="adverse_events",
        columns={
            "event_id": "str",
            "trial_id": "str",
            "site_id": "str",
            "patient_code": "str",
            "event_date": "date",
            "adverse_event_term": "str",
            "severity": "str",
            "seriousness": "str",
            "causality_assessment": "str",
            "outcome": "str",
            "reported_by": "str",
        },
        primary_key="event_id",
        required_columns=["event_id", "trial_id", "site_id"],
        foreign_keys=[
            ForeignKey("trial_id", "clinical_trials", "trial_id"),
            ForeignKey("site_id", "trial_sites", "site_id"),
        ],
    ),
    "research_documents": TableSchema(
        name="research_documents",
        columns={
            "doc_id": "str",
            "compound_id": "str",
            "trial_id": "str",
            "doc_type": "str",
            "title": "str",
            "author": "str",
            "date": "date",
            "full_text": "str",
            "tags": "str",
        },
        primary_key="doc_id",
        required_columns=["doc_id"],
        foreign_keys=[
            ForeignKey("compound_id", "compounds", "compound_id", nullable=True),
            ForeignKey("trial_id", "clinical_trials", "trial_id", nullable=True),
        ],
    ),
    "agent_interaction_logs": TableSchema(
        name="agent_interaction_logs",
        columns={
            "log_id": "str",
            "session_id": "str",
            "timestamp": "datetime",
            "user_role": "str",
            "user_query": "str",
            "agent_invoked": "str",
            "tool_called": "str",
            "response_summary": "str",
            "latency_ms": "int",
            "tokens_used": "int",
            "feedback_rating": "int",
            "escalated_flag": "bool",
        },
        primary_key="log_id",
        required_columns=["log_id", "session_id"],
    ),
}

# Load order that respects FK dependencies (parents before children).
LOAD_ORDER: List[str] = [
    "compounds",
    "clinical_trials",
    "trial_sites",
    "lab_results",
    "adverse_events",
    "research_documents",
    "agent_interaction_logs",
]
