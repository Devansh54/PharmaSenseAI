"""Phase 1 initial source schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-27

"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compounds",
        sa.Column("compound_id", sa.String(20), primary_key=True),
        sa.Column("compound_name", sa.String(100)),
        sa.Column("chemical_class", sa.String(100)),
        sa.Column("therapeutic_area", sa.String(100)),
        sa.Column("target_protein", sa.String(100)),
        sa.Column("mechanism_of_action", sa.Text()),
        sa.Column("discovery_phase", sa.String(50)),
        sa.Column("molecular_weight_da", sa.Numeric()),
        sa.Column("solubility_mg_ml", sa.Numeric()),
        sa.Column("toxicity_score", sa.Numeric()),
        sa.Column("lead_scientist", sa.String(150)),
        sa.Column("synthesis_date", sa.Date()),
        sa.Column("created_at", sa.Date()),
    )

    op.create_table(
        "clinical_trials",
        sa.Column("trial_id", sa.String(20), primary_key=True),
        sa.Column("compound_id", sa.String(20), sa.ForeignKey("compounds.compound_id"), nullable=False),
        sa.Column("trial_phase", sa.String(50)),
        sa.Column("therapeutic_area", sa.String(100)),
        sa.Column("sponsor", sa.String(150)),
        sa.Column("start_date", sa.Date()),
        sa.Column("planned_end_date", sa.Date()),
        sa.Column("actual_end_date", sa.Date()),
        sa.Column("status", sa.String(50)),
        sa.Column("target_enrollment", sa.Integer()),
        sa.Column("actual_enrollment", sa.Integer()),
        sa.Column("primary_endpoint", sa.String(200)),
    )

    op.create_table(
        "trial_sites",
        sa.Column("site_id", sa.String(20), primary_key=True),
        sa.Column("trial_id", sa.String(20), sa.ForeignKey("clinical_trials.trial_id"), nullable=False),
        sa.Column("site_name", sa.String(200)),
        sa.Column("country", sa.String(100)),
        sa.Column("principal_investigator", sa.String(150)),
        sa.Column("enrollment_count", sa.Integer()),
        sa.Column("site_status", sa.String(50)),
    )

    op.create_table(
        "lab_results",
        sa.Column("result_id", sa.String(20), primary_key=True),
        sa.Column("compound_id", sa.String(20), sa.ForeignKey("compounds.compound_id"), nullable=False),
        sa.Column("experiment_type", sa.String(100)),
        sa.Column("result_value", sa.Numeric()),
        sa.Column("unit", sa.String(50)),
        sa.Column("result_date", sa.Date()),
        sa.Column("technician", sa.String(150)),
        sa.Column("pass_fail", sa.String(10)),
    )

    op.create_table(
        "adverse_events",
        sa.Column("event_id", sa.String(20), primary_key=True),
        sa.Column("trial_id", sa.String(20), sa.ForeignKey("clinical_trials.trial_id"), nullable=False),
        sa.Column("site_id", sa.String(20), sa.ForeignKey("trial_sites.site_id"), nullable=False),
        sa.Column("patient_code", sa.String(20)),
        sa.Column("event_date", sa.Date()),
        sa.Column("adverse_event_term", sa.String(100)),
        sa.Column("severity", sa.String(20)),
        sa.Column("seriousness", sa.String(20)),
        sa.Column("causality_assessment", sa.String(30)),
        sa.Column("outcome", sa.String(50)),
        sa.Column("reported_by", sa.String(100)),
    )

    op.create_table(
        "research_documents",
        sa.Column("doc_id", sa.String(20), primary_key=True),
        sa.Column("compound_id", sa.String(20), sa.ForeignKey("compounds.compound_id"), nullable=True),
        sa.Column("trial_id", sa.String(20), sa.ForeignKey("clinical_trials.trial_id"), nullable=True),
        sa.Column("doc_type", sa.String(50)),
        sa.Column("title", sa.String(300)),
        sa.Column("author", sa.String(150)),
        sa.Column("date", sa.Date()),
        sa.Column("full_text", sa.Text()),
        sa.Column("tags", sa.String(300)),
    )

    op.create_table(
        "agent_interaction_logs",
        sa.Column("log_id", sa.String(20), primary_key=True),
        sa.Column("session_id", sa.String(20)),
        sa.Column("timestamp", sa.DateTime()),
        sa.Column("user_role", sa.String(100)),
        sa.Column("user_query", sa.Text()),
        sa.Column("agent_invoked", sa.String(100)),
        sa.Column("tool_called", sa.String(100)),
        sa.Column("response_summary", sa.Text()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("tokens_used", sa.Integer()),
        sa.Column("feedback_rating", sa.Integer()),
        sa.Column("escalated_flag", sa.Boolean()),
    )

    op.create_table(
        "data_provenance",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_file", sa.String(200), nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_started_at", sa.DateTime(), nullable=False),
        sa.Column("run_finished_at", sa.DateTime()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("tables_loaded", sa.Text()),
        sa.Column("error_message", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("ingestion_runs")
    op.drop_table("data_provenance")
    op.drop_table("agent_interaction_logs")
    op.drop_table("research_documents")
    op.drop_table("adverse_events")
    op.drop_table("lab_results")
    op.drop_table("trial_sites")
    op.drop_table("clinical_trials")
    op.drop_table("compounds")
