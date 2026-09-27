"""SQLAlchemy ORM models mirroring the PostgreSQL source schema.

These models are the source of truth for Alembic's initial migration and
for the transactional ingestion coercion step.
"""
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Compound(Base):
    __tablename__ = "compounds"

    compound_id = Column(String(20), primary_key=True)
    compound_name = Column(String(100))
    chemical_class = Column(String(100))
    therapeutic_area = Column(String(100))
    target_protein = Column(String(100))
    mechanism_of_action = Column(Text)
    discovery_phase = Column(String(50))
    molecular_weight_da = Column(Numeric)
    solubility_mg_ml = Column(Numeric)
    toxicity_score = Column(Numeric)
    lead_scientist = Column(String(150))
    synthesis_date = Column(Date)
    created_at = Column(Date)


class ClinicalTrial(Base):
    __tablename__ = "clinical_trials"

    trial_id = Column(String(20), primary_key=True)
    compound_id = Column(String(20), ForeignKey("compounds.compound_id"), nullable=False)
    trial_phase = Column(String(50))
    therapeutic_area = Column(String(100))
    sponsor = Column(String(150))
    start_date = Column(Date)
    planned_end_date = Column(Date)
    actual_end_date = Column(Date)
    status = Column(String(50))
    target_enrollment = Column(Integer)
    actual_enrollment = Column(Integer)
    primary_endpoint = Column(String(200))


class TrialSite(Base):
    __tablename__ = "trial_sites"

    site_id = Column(String(20), primary_key=True)
    trial_id = Column(String(20), ForeignKey("clinical_trials.trial_id"), nullable=False)
    site_name = Column(String(200))
    country = Column(String(100))
    principal_investigator = Column(String(150))
    enrollment_count = Column(Integer)
    site_status = Column(String(50))


class LabResult(Base):
    __tablename__ = "lab_results"

    result_id = Column(String(20), primary_key=True)
    compound_id = Column(String(20), ForeignKey("compounds.compound_id"), nullable=False)
    experiment_type = Column(String(100))
    result_value = Column(Numeric)
    unit = Column(String(50))
    result_date = Column(Date)
    technician = Column(String(150))
    pass_fail = Column(String(10))


class AdverseEvent(Base):
    __tablename__ = "adverse_events"

    event_id = Column(String(20), primary_key=True)
    trial_id = Column(String(20), ForeignKey("clinical_trials.trial_id"), nullable=False)
    site_id = Column(String(20), ForeignKey("trial_sites.site_id"), nullable=False)
    patient_code = Column(String(20))
    event_date = Column(Date)
    adverse_event_term = Column(String(100))
    severity = Column(String(20))
    seriousness = Column(String(20))
    causality_assessment = Column(String(30))
    outcome = Column(String(50))
    reported_by = Column(String(100))


class ResearchDocument(Base):
    __tablename__ = "research_documents"

    doc_id = Column(String(20), primary_key=True)
    compound_id = Column(String(20), ForeignKey("compounds.compound_id"), nullable=True)
    trial_id = Column(String(20), ForeignKey("clinical_trials.trial_id"), nullable=True)
    doc_type = Column(String(50))
    title = Column(String(300))
    author = Column(String(150))
    date = Column(Date)
    full_text = Column(Text)
    tags = Column(String(300))


class AgentInteractionLog(Base):
    __tablename__ = "agent_interaction_logs"

    log_id = Column(String(20), primary_key=True)
    session_id = Column(String(20))
    timestamp = Column(DateTime)
    user_role = Column(String(100))
    user_query = Column(Text)
    agent_invoked = Column(String(100))
    tool_called = Column(String(100))
    response_summary = Column(Text)
    latency_ms = Column(Integer)
    tokens_used = Column(Integer)
    feedback_rating = Column(Integer)
    escalated_flag = Column(Boolean)


class DataProvenance(Base):
    __tablename__ = "data_provenance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_file = Column(String(200), nullable=False)
    sha256_hash = Column(String(64), nullable=False)
    row_count = Column(Integer, nullable=False)
    column_count = Column(Integer, nullable=False)
    captured_at = Column(DateTime, nullable=False)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_started_at = Column(DateTime, nullable=False)
    run_finished_at = Column(DateTime)
    status = Column(String(20), nullable=False)
    tables_loaded = Column(Text)  # JSON-encoded dict of table -> row count
    error_message = Column(Text)
