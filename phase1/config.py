"""Configuration for Phase 1 data foundation tooling."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "pharmasense_synthetic_data_csv"

CSV_FILES = {
    "compounds": DATA_DIR / "compounds.csv",
    "clinical_trials": DATA_DIR / "clinical_trials.csv",
    "trial_sites": DATA_DIR / "trial_sites.csv",
    "lab_results": DATA_DIR / "lab_results.csv",
    "adverse_events": DATA_DIR / "adverse_events.csv",
    "research_documents": DATA_DIR / "research_documents.csv",
    "agent_interaction_logs": DATA_DIR / "agent_interaction_logs.csv",
}

REPORTS_DIR = REPO_ROOT / "phase1" / "reports"
PROVENANCE_DIR = REPO_ROOT / "phase1" / "provenance"

DATABASE_URL = os.environ.get(
    "PHARMASENSE_DATABASE_URL",
    "postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense",
)
